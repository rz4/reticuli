"""reticuli.reference: an independent implementation of spec/identity.md.

Parses a claim's recipe and computes the identity root and the build
digest directly from the spec, without importing anything from
`reticuli.kernel` -- this is the second implementation the conformance
vectors (`spec/vectors/`) cross-check the kernel against. Stdlib only.

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>
"""
import datetime
import hashlib
import json
import os
import stat
import sys

import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
FORMAT = 3
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})


class ReferenceError(Exception):
    """A refusal with a reason."""


# --- path and byte boundaries ----------------------------------------------

def _safe_path(base: str, name) -> str:
    """Resolve `name` to a real path under `base`, refusing anything that
    escapes it or passes through a symlink (spec/identity.md, "File hashing
    rules")."""
    if not isinstance(name, str) or not name:
        raise ReferenceError(f"path name must be a non-empty string: {name!r}")
    if os.path.isabs(name):
        raise ReferenceError(f"path name must not be absolute: {name!r}")
    parts = name.split("/")
    if any(p in ("", "..") for p in parts):
        raise ReferenceError(f"path name must not escape the claim: {name!r}")

    real_base = os.path.realpath(base)
    walked = real_base
    for part in parts:
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise ReferenceError(f"path name must not pass through a symlink: {name!r}")

    resolved = os.path.realpath(os.path.join(real_base, name))
    if resolved != real_base and not resolved.startswith(real_base + os.sep):
        raise ReferenceError(f"path name escapes the claim: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    """sha256 of a file's bytes; refuses anything but a regular file with a
    single hard link (spec/identity.md, "File hashing rules")."""
    try:
        st = os.lstat(path)
    except OSError as e:
        raise ReferenceError(f"cannot stat {path!r}: {e}") from e
    if not stat.S_ISREG(st.st_mode):
        raise ReferenceError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ReferenceError(f"file must have a single hard link: {path!r}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- canonical serialization (spec/identity.md) -----------------------------

def _refuse_datetimes(obj, where: str) -> None:
    """TOML date/time values have no canonical JSON form; refuse them."""
    if isinstance(obj, (datetime.date, datetime.time)):
        raise ReferenceError(f"TOML date/time values are refused at sealing: {where}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _refuse_datetimes(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _refuse_datetimes(v, f"{where}[{i}]")


def _canonical_json(obj) -> bytes:
    """`json.dumps(obj, sort_keys=True)`, encoded UTF-8: sorted keys, default
    (non-compact) separators, ASCII escaping, exact-decimal integers, floats
    as CPython's `repr` -- everything `json.dumps` already does with no other
    argument changed."""
    return json.dumps(obj, sort_keys=True).encode("utf-8")


# --- recipe parsing (spec/claim-format.md) ----------------------------------

def _recipe_path(d: str) -> str:
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ReferenceError(f"no recipe ({RECIPE} or {LEGACY_RECIPE}) in {d!r}")


def _step_class(step: dict) -> str:
    declared = step.get("class")
    if declared is not None:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def _read_inputs_manifest(path: str) -> list:
    """One path per line, `[<sha256>  ]<path>`; blanks and `#` comments
    ignored (spec/claim-format.md, "inputs_manifest")."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise ReferenceError(f"cannot read inputs manifest {path!r}: {e}") from e

    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, tail = line.partition(" ")
        if len(head) == 64 and tail.strip():
            paths.append(tail.strip())
        else:
            paths.append(line)
    return paths


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under claim directory `d`; refuses in
    band (`ReferenceError`) rather than crashing on malformed input."""
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ReferenceError(f"cannot read recipe {path!r}: {e}") from e

    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise ReferenceError(f"recipe {path!r} is not valid UTF-8: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ReferenceError(f"malformed recipe {path!r}: {e}") from e

    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ReferenceError(f"recipe {path!r} has no [claim] table")

    claim = doc["claim"]
    name = claim.get("name")
    if not isinstance(name, str):
        raise ReferenceError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ReferenceError(f"[claim] format must be a positive integer: {fmt!r}")
    if fmt > FORMAT:
        raise ReferenceError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise ReferenceError("[claim] inputs must be a list of paths")
    for p in inputs:
        _safe_path(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        _safe_path(d, manifest)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ReferenceError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ReferenceError(f"a step must be a table: {step!r}")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ReferenceError(f"a step kind must be one of {sorted(KINDS)}: {kind!r}")
        _safe_path(d, step.get("output"))
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ReferenceError(f"a gate step needs a string run: {step!r}")
        step["class"] = _step_class(step)

    return doc


def _inputs(parsed: dict, d: str) -> list:
    """Every pinned input path: `[claim] inputs`, plus an `inputs_manifest`
    (itself a pinned input) and the paths it names, in that order."""
    claim = parsed["claim"]
    paths = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_inputs_manifest(os.path.join(d, manifest)))
    return paths


def _steps(parsed: dict) -> list:
    return parsed.get("step", [])


def _produces(parsed: dict) -> list:
    return [s for s in _steps(parsed) if s["kind"] == "produce"]


# --- identity (spec/identity.md) --------------------------------------------

def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root's preimage: at format 3, every
    step's `guidance`/`request` key is stripped first (producer guidance
    cannot decide acceptance, so it is not identity-bearing)."""
    fmt = parsed["claim"].get("format", 1)
    doc = dict(parsed)
    if fmt >= 3:
        doc["step"] = [
            {k: v for k, v in step.items() if k not in GUIDANCE_KEYS}
            for step in doc.get("step", [])
        ]
    _refuse_datetimes(doc, "recipe")
    return doc


def _parts(parsed: dict, d: str) -> dict:
    parts = {"digest": DIGEST,
             "recipe": _canonical_json(_preimage_recipe(parsed)).decode("ascii")}
    for path in _inputs(parsed, d):
        parts[f"input:{path}"] = _hash_file(os.path.join(d, path))
    for step in _steps(parsed):
        if step["class"] not in ("generated", "free"):
            parts[f"pinned:{step['output']}"] = _hash_file(os.path.join(d, step["output"]))
    return parts


def root(d: str) -> str:
    """The claim's identity: SHA-256 over the canonical `parts` map."""
    parsed = load_recipe(d)
    return hashlib.sha256(_canonical_json(_parts(parsed, d))).hexdigest()


def build_digest(d: str) -> str:
    """SHA-256 over the generated bytes present under claim directory `d`:
    one `[output, sha256]` pair per `produce` step whose class is
    `generated`/`free`, in recipe order, excluding any step with a `from`
    source and omitting any output not present on disk."""
    parsed = load_recipe(d)
    pairs = []
    for step in _produces(parsed):
        if step["class"] not in ("generated", "free"):
            continue
        if "from" in step:
            continue
        path = os.path.join(d, step["output"])
        if os.path.isfile(path):
            pairs.append([step["output"], _hash_file(path)])
    return hashlib.sha256(_canonical_json(pairs)).hexdigest()


# --- CLI ---------------------------------------------------------------------

def main(argv) -> int:
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim-dir>",
              file=sys.stderr)
        return 2
    verb, claim_dir = argv
    try:
        if verb == "root":
            print(root(claim_dir))
        else:
            print(build_digest(claim_dir))
    except ReferenceError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
