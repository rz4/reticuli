"""reticuli.reference: an independent implementation of the identity
computation (`spec/identity.md`), built from the spec and the conformance
vectors alone, to cross-check `reticuli.kernel`.

A claim's root is a SHA-256 digest over a string-to-string map: the
algorithm name, the claim's parsed recipe (canonically serialized, with
producer guidance stripped from format 3 and the step list canonicalized
from format 4), the hash of every pinned input, and the hash of every
non-generated step output. It never covers the bytes of a generated
output, so regrowing an implementation never moves the root.

The build digest is a separate SHA-256 over the bytes of the generated
outputs actually present on disk (a `from`-sourced output excluded, an
absent one omitted), the digest a signature over concrete bytes binds.

Both use the same canonical JSON: `json.dumps(x, sort_keys=True)` with
every other argument left at its default -- sorted keys, default
(non-compact) separators, ASCII-escaped, exact-decimal integers,
`repr`-shortest floats. A TOML date/time value has no such form and is
refused.

Command line:

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>

prints the 64-lowercase-hex answer on its own line.

Stdlib only.
"""
import datetime
import hashlib
import json
import os
import stat
import sys
import tomllib
from pathlib import PurePosixPath

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
FORMAT = 4
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})


class ClaimError(Exception):
    """A refusal with a reason."""


# ---- the path and bytes boundaries -----------------------------------------

def _safe(base: str, name: str) -> str:
    """Resolve a recipe-declared name under `base`, refusing any escape:
    an empty or absolute name, a `..`/`.` component, or any component
    that is a symlink -- even one whose target stays inside the claim."""
    if not isinstance(name, str) or not name:
        raise ClaimError("path boundary: refusing an empty path")
    if os.path.isabs(name):
        raise ClaimError(f"path boundary: refusing an absolute path {name!r}")
    parts = PurePosixPath(name).parts
    if not parts or any(p in ("..", ".") for p in parts):
        raise ClaimError(f"path boundary: refusing {name!r}")
    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"path boundary: refusing a symlink component in {name!r}")
    if cur != base_real and not cur.startswith(base_real + os.sep):
        raise ClaimError(f"path boundary: {name!r} escapes the claim")
    return cur


def _hash_file(path: str) -> str:
    """A plain sha256 of a file's bytes; refuses anything but a regular,
    singly linked file."""
    st = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"the bytes boundary refuses a non-regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"the bytes boundary refuses a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- the recipe -------------------------------------------------------------

def recipe_path(d: str) -> str:
    """The recipe file under claim directory `d`: `reticuli.toml`
    preferred, `claim.toml` read under its legacy name."""
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe found: neither {RECIPE!r} nor {LEGACY_RECIPE!r} in {d!r}")


def _validate(parsed) -> None:
    if not isinstance(parsed, dict):
        raise ClaimError("a recipe must be a TOML table")
    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")
    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("every step must be a table")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(f"a step kind must be one of {sorted(KINDS)}, got {kind!r}")
        if not isinstance(step.get("output"), str) or not step["output"]:
            raise ClaimError("every step needs a string output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("a gate step needs a string run command")


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at claim directory `d`; refuses,
    as a `ClaimError`, anything not valid TOML or not shaped per
    `spec/claim-format.md`."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    _validate(parsed)
    return parsed


def _steps(parsed: dict) -> list:
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    return [s["output"] for s in produces(parsed)
            if s.get("class", "generated") == "generated"]


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one entry per line, optionally
    `<sha256>  <path>`, blank lines and `#` comments ignored."""
    paths = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            paths.append(parts[-1] if len(parts) > 1 else parts[0])
    return paths


def _inputs(parsed: dict, d: str) -> list:
    """The claim's pinned input paths: `[claim] inputs`, or the contents
    of `[claim] inputs_manifest` when that is declared instead."""
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        return _read_input_manifest(_safe(d, manifest))
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    return list(inputs)


# ---- canonical JSON (spec/identity.md) --------------------------------------

def _canonical_json(obj) -> str:
    """`json.dumps(x, sort_keys=True)` with every other argument at its
    default: sorted keys, default separators, ASCII-escaped, exact-decimal
    integers, repr-shortest floats. A TOML date/time value is refused."""
    def _refuse(o):
        if isinstance(o, (datetime.date, datetime.time)):
            raise ClaimError(
                "TOML date/time values are refused at sealing: "
                "JSON gives them no canonical form"
            )
        raise TypeError(f"object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, sort_keys=True, default=_refuse)


# ---- the identity computation ------------------------------------------------

def _claim_format(parsed: dict) -> int:
    """The claim's declared format: absent means 1. Refuses a format
    newer than this implementation understands, in words."""
    fmt = parsed.get("claim", {}).get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it"
        )
    return fmt


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root preimage: at format 3+, every
    step's guidance (`guidance`/`request`) is stripped; at format 4+, the
    step list is further sorted into the lexicographic order of each
    step's own canonical encoding."""
    fmt = _claim_format(parsed)
    preimage = dict(parsed)
    steps = [dict(s) for s in parsed.get("step", [])]
    if fmt >= 3:
        for step in steps:
            for key in GUIDANCE_KEYS:
                step.pop(key, None)
    if fmt >= 4:
        steps.sort(key=_canonical_json)
    preimage["step"] = steps
    return preimage


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map the root is computed over."""
    parts = {"digest": DIGEST, "recipe": _canonical_json(_preimage_recipe(parsed))}

    for path in _inputs(parsed, d):
        parts[f"input:{path}"] = _hash_file(_safe(d, path))

    for step in parsed.get("step", []):
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_class) != "generated":
            output = step["output"]
            parts[f"pinned:{output}"] = _hash_file(_safe(d, output))

    return parts


def root(d: str) -> str:
    """The claim's identity at directory `d`:
    `sha256(canonical_json(_parts(recipe, d)))`."""
    parsed = load_recipe(d)
    return _sha256_hex(_canonical_json(_parts(parsed, d)).encode("utf-8"))


def build_digest(d: str) -> str:
    """The digest of the generated bytes present under claim directory
    `d`: sha256 of the canonical JSON of a sorted `[output, sha256(bytes)]`
    list, one entry per produce step whose class is `generated` and which
    has no `from`. An absent output is omitted; none at all gives the
    digest of the empty list."""
    parsed = load_recipe(d)
    pairs = []
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") != "generated":
            continue
        if "from" in step:
            continue
        output = step["output"]
        path = _safe(d, output)
        if not os.path.exists(path):
            continue
        pairs.append([output, _hash_file(path)])
    pairs.sort()
    return _sha256_hex(_canonical_json(pairs).encode("utf-8"))


# ---- command line ------------------------------------------------------------

def main(argv) -> int:
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: reticuli.reference {root|digest} <claim-dir>", file=sys.stderr)
        return 2
    verb, claim_dir = argv
    try:
        answer = root(claim_dir) if verb == "root" else build_digest(claim_dir)
    except ClaimError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
