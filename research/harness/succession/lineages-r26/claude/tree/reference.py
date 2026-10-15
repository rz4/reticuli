"""A second, independent implementation of the identity computation.

Computes `root(d)` and `build_digest(d)` for the claim directory `d`,
exactly as `spec/identity.md` specifies: a SHA-256 digest over a canonical
JSON preimage built from the parsed recipe, the claim's pinned inputs, and
its pinned step outputs. Producer guidance (`guidance`/`request`) is
stripped from the preimage at format 3+, and the step list is canonically
reordered at format 4+.

This module is deliberately self-contained -- it shares no code with
`reticuli.kernel` -- so that the two implementations agreeing on every
conformance vector in `spec/vectors/` is evidence about the specification,
not about a shared bug.

Stdlib only.

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
GUIDANCE_KEYS = ("guidance", "request")
DIGEST = "sha256"


class ClaimError(Exception):
    """A refusal with a reason."""


# -- finding and parsing the recipe ------------------------------------------


def recipe_path(d: str) -> str:
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe found in {d!r}: expected {RECIPE} or {LEGACY_RECIPE}")


def load_recipe(d: str) -> dict:
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    if not isinstance(parsed, dict) or not isinstance(parsed.get("claim"), dict):
        raise ClaimError("a recipe needs a [claim] table")
    if not isinstance(parsed["claim"].get("name"), str):
        raise ClaimError("[claim] name is required and must be a string")
    return parsed


# -- the path boundary --------------------------------------------------------


def _safe(base: str, name: str) -> str:
    """Resolve `name` to a real path under `base`, or refuse.

    Refuses an absolute or empty name, a `..` or `.` component, and any
    symlink component -- even one whose target stays inside the claim.
    """
    if not name:
        raise ClaimError("a claim path must not be empty")
    if os.path.isabs(name):
        raise ClaimError(f"a claim path must not be absolute: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", "..", ".") for p in parts):
        raise ClaimError(f"a claim path must not escape the claim: {name!r}")

    base_real = os.path.realpath(base)
    walked = base_real
    for part in parts:
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise ClaimError(f"a claim path must not pass through a symlink: {name!r}")

    resolved = os.path.realpath(os.path.join(base_real, *parts))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ClaimError(f"a claim path must not escape the claim: {name!r}")
    return resolved


# -- the bytes boundary --------------------------------------------------------


def _hash_file(path: str) -> str:
    """sha256 hex digest of a file's bytes.

    Refuses anything that is not a plain regular file with exactly one
    hard link: a FIFO, device, socket, directory, or a hardlink to an
    outside inode must not be silently hashed as if it were claim content.
    """
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"not a regular file: {path!r}")
    if st.st_nlink != 1:
        raise ClaimError(f"refuses a file with more than one hard link: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_declared(d: str, path: str) -> str:
    resolved = _safe(d, path)
    if not os.path.exists(resolved):
        raise ClaimError(f"declared path is missing: {path!r}")
    return _hash_file(resolved)


# -- canonical JSON ------------------------------------------------------------


def _refuse_dates(obj) -> None:
    """TOML date/time values have no canonical JSON form (spec/identity.md)."""
    if isinstance(obj, (datetime.date, datetime.time)):
        raise ClaimError("a TOML date or time value cannot enter the root preimage")
    if isinstance(obj, dict):
        for v in obj.values():
            _refuse_dates(v)
    elif isinstance(obj, list):
        for v in obj:
            _refuse_dates(v)


def _canonical_json(obj) -> str:
    """`json.dumps(obj, sort_keys=True)`: sorted keys, default separators, ASCII-escaped."""
    _refuse_dates(obj)
    return json.dumps(obj, sort_keys=True)


# -- the recipe as embedded in the preimage ------------------------------------


def _claim_format(parsed: dict) -> int:
    return parsed.get("claim", {}).get("format", 1)


def _strip_guidance(step: dict) -> dict:
    return {k: v for k, v in step.items() if k not in GUIDANCE_KEYS}


def _preimage_recipe(parsed: dict) -> dict:
    """Format 3+ strips every step's guidance/request; format 4+ additionally
    sorts the (already-stripped) step list by each step's own canonical JSON
    encoding, so authoring order cannot move the root."""
    fmt = _claim_format(parsed)
    out = dict(parsed)
    if "step" in parsed:
        steps = list(parsed["step"])
        if fmt >= 3:
            steps = [_strip_guidance(s) for s in steps]
        if fmt >= 4:
            steps = sorted(steps, key=lambda s: json.dumps(s, sort_keys=True))
        out["step"] = steps
    return out


# -- declared inputs and pinned outputs ----------------------------------------


def _read_input_manifest(path: str) -> list:
    """One entry per line, optionally `<sha256>  <path>`; blank lines and
    `#` comments are ignored."""
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            paths.append(parts[1] if len(parts) == 2 and len(parts[0]) == 64 else parts[0])
    return paths


def _declared_inputs(d: str, parsed: dict) -> list:
    """Every pinned input path: declared directly, plus any named by a manifest."""
    paths = list(parsed.get("claim", {}).get("inputs", []))
    manifest = parsed.get("claim", {}).get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_input_manifest(_safe(d, manifest)))
    return paths


def _default_class(step: dict) -> str:
    return "generated" if step.get("kind") == "produce" else "pinned"


def _pinned_outputs(parsed: dict) -> list:
    """Every step output whose class is not `generated` -- pinned into the root."""
    out = []
    for step in parsed.get("step", []):
        if step.get("class", _default_class(step)) != "generated":
            out.append(step["output"])
    return out


# -- the root -------------------------------------------------------------------


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map whose canonical serialization the root hashes."""
    parts = {
        "digest": DIGEST,
        "recipe": _canonical_json(_preimage_recipe(parsed)),
    }
    for path in _declared_inputs(d, parsed):
        parts[f"input:{path}"] = _hash_declared(d, path)
    for path in _pinned_outputs(parsed):
        parts[f"pinned:{path}"] = _hash_declared(d, path)
    return parts


def root(d: str) -> str:
    """The claim's identity hash."""
    parsed = load_recipe(d)
    return hashlib.sha256(_canonical_json(_parts(parsed, d)).encode("utf-8")).hexdigest()


# -- the build digest -----------------------------------------------------------


def _generated_entries(d: str, parsed: dict) -> list:
    """`[path, sha256]` pairs for every present `generated` output with no `from`."""
    entries = []
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", _default_class(step)) != "generated" or "from" in step:
            continue
        resolved = _safe(d, step["output"])
        if not os.path.exists(resolved):
            continue
        entries.append([step["output"], _hash_file(resolved)])
    entries.sort(key=lambda e: e[0])
    return entries


def build_digest(d: str) -> str:
    """The digest of the generated bytes present -- what a signature binds."""
    parsed = load_recipe(d)
    entries = _generated_entries(d, parsed)
    return hashlib.sha256(_canonical_json(entries).encode("utf-8")).hexdigest()


# -- command-line entry point ----------------------------------------------------


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim-dir>",
              file=sys.stderr)
        return 2
    verb, d = argv
    try:
        print(root(d) if verb == "root" else build_digest(d))
    except ClaimError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
