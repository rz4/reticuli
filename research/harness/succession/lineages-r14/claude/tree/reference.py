"""reticuli.reference -- an independent, stdlib-only implementation of the
identity computation (spec/identity.md) and the build digest
(spec/identity.md), used as the conformance vectors' second implementation
and as a conformant implementation `spec/vectors/run.py` can be pointed at:

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>

Each prints one 64-character lowercase-hex digest to stdout. This module
does not import anything from `reticuli.kernel` or `reticuli._kernel`: it is
a second, independently-written reading of the spec, so that the vectors'
claim -- the kernel and this module agree -- is not circular.
"""
import hashlib
import json
import os
import stat
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
MAX_FORMAT = 4
GUIDANCE_KEYS = ("guidance", "request")
_HEXDIGITS = frozenset("0123456789abcdef")


class ClaimError(Exception):
    """A refusal with a reason."""


# -- the path boundary (spec/identity.md: file hashing rules) --------------

def _safe(base: str, name: str) -> str:
    """Resolve `name` inside `base`; refuse anything that escapes the claim
    or crosses a symlink."""
    if not name or os.path.isabs(name):
        raise ClaimError(f"refused path: {name!r}")
    norm = os.path.normpath(name)
    if norm in (os.curdir, os.pardir):
        raise ClaimError(f"refused path: {name!r}")
    parts = norm.split(os.sep)
    if any(part == os.pardir or part == "" for part in parts):
        raise ClaimError(f"refused path: {name!r} escapes the claim")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        if os.path.islink(cur):
            raise ClaimError(f"refused path: {name!r} crosses a symlink")
        cur = os.path.join(cur, part)
    if os.path.islink(cur):
        raise ClaimError(f"refused path: {name!r} crosses a symlink")

    resolved = os.path.join(base_real, norm)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ClaimError(f"refused path: {name!r} escapes the claim")
    return resolved


def _hashed(path: str) -> str:
    """sha256 of a declared file's bytes; refuses anything but a regular
    file with a single hard link."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError as e:
        raise ClaimError(f"cannot stat {path!r}: {e}") from e
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"refused {path!r}: not a regular file")
    if st.st_nlink != 1:
        raise ClaimError(f"refused {path!r}: has more than one hard link")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# -- parsing the recipe (spec/claim-format.md) ------------------------------

def recipe_path(d: str) -> str:
    """The path to `d`'s recipe file, preferring the canonical name."""
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe found in {d!r} (expected {RECIPE} or {LEGACY_RECIPE})")


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; refuse, never crash, on anything
    wrong -- the recipe is untrusted input."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ClaimError(f"recipe {path!r} is not valid UTF-8: {e}") from e

    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} is missing a [claim] table")

    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > MAX_FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this implementation "
            f"understands (format {MAX_FORMAT}); upgrade to read it"
        )

    for step in doc.get("step", []):
        if not isinstance(step, dict):
            raise ClaimError(f"recipe {path!r}: each step must be a table")
        if step.get("kind") not in ("produce", "gate"):
            raise ClaimError(f"recipe {path!r}: bad step kind {step.get('kind')!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"recipe {path!r}: every step needs an 'output'")

    return doc


def _claim_format(doc: dict) -> int:
    """The recipe's declared format; absent means 1 (spec/claim-format.md)."""
    return doc.get("claim", {}).get("format", 1)


def _read_input_manifest(d: str, manifest_name: str) -> list:
    """Parse an `inputs_manifest` file: one path per line, optionally
    `<sha256>  <path>`; blank lines and `#` comments are ignored."""
    path = _safe(d, manifest_name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise ClaimError(f"cannot read inputs manifest {manifest_name!r}: {e}") from e

    paths = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        if len(head) == 64 and rest.strip() and all(c in _HEXDIGITS for c in head.lower()):
            entry = rest.strip()
        else:
            entry = line
        paths.append(entry)
    return paths


def _inputs(d: str, doc: dict) -> list:
    """Every pinned input path the recipe declares, `inputs` and
    `inputs_manifest` combined."""
    claim = doc.get("claim", {})
    result = list(claim.get("inputs") or [])
    manifest = claim.get("inputs_manifest")
    if manifest:
        result.extend(_read_input_manifest(d, manifest))
    return result


# -- the identity computation (spec/identity.md) ----------------------------

def _canonical_json(obj) -> str:
    """`json.dumps(x, sort_keys=True)` with every other argument at its
    default: sorted keys, default separators, ASCII-escaped non-ASCII."""
    return json.dumps(obj, sort_keys=True)


def _preimage_recipe(doc: dict) -> dict:
    """The recipe exactly as it enters the root preimage: guidance stripped
    at format 3+, the step list canonicalized to a set at format 4+."""
    fmt = _claim_format(doc)
    out = dict(doc)
    if "step" in out:
        steps = [dict(s) for s in out["step"]]
        if fmt >= 3:
            for step in steps:
                for key in GUIDANCE_KEYS:
                    step.pop(key, None)
        if fmt >= 4:
            steps.sort(key=_canonical_json)
        out["step"] = steps
    return out


def root(d: str) -> str:
    """A claim's identity: a SHA-256 over the canonical `parts` map built
    from the recipe, its pinned inputs, and its pinned/validated step
    outputs -- never the bytes of a `generated` output."""
    doc = load_recipe(d)
    parts = {
        "digest": "sha256",
        "recipe": _canonical_json(_preimage_recipe(doc)),
    }

    for path in _inputs(d, doc):
        parts[f"input:{path}"] = _hashed(_safe(d, path))

    for step in doc.get("step", []):
        output = step.get("output")
        if not isinstance(output, str):
            continue
        cls = step.get("class")
        if cls is None:
            cls = "generated" if step.get("kind") == "produce" else "pinned"
        if cls == "generated":
            continue
        parts[f"pinned:{output}"] = _hashed(_safe(d, output))

    return hashlib.sha256(_canonical_json(parts).encode("utf-8")).hexdigest()


def build_digest(d: str) -> str:
    """The digest of the generated bytes present in `d`: a `from` output is
    excluded, an absent output is omitted, the empty list hashes for none."""
    doc = load_recipe(d)
    entries = []
    for step in doc.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") != "generated":
            continue
        if step.get("from") is not None:
            continue
        output = step.get("output")
        full = _safe(d, output)
        if not os.path.isfile(full):
            continue
        entries.append([output, _hashed(full)])
    entries.sort()
    return hashlib.sha256(_canonical_json(entries).encode("utf-8")).hexdigest()


# -- CLI: one digest per invocation, for spec/vectors/run.py ---------------

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference <root|digest> <claim-dir>",
              file=sys.stderr)
        return 2
    command, d = argv
    try:
        print(root(d) if command == "root" else build_digest(d))
    except ClaimError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
