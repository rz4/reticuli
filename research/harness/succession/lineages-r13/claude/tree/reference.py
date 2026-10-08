"""An independent reference implementation of the identity computation
(spec/identity.md): `root` and `build_digest`, computed from a claim
directory's recipe and declared inputs/outputs alone, with no dependency on
`reticuli.kernel`. Stdlib only.

Runnable as a conformance-test subject:

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference build-digest <claim-dir>

Each prints one 64-character lowercase-hex digest on stdout.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
GUIDANCE_KEYS = ("guidance", "request")
KINDS = ("produce", "gate")
_HEXDIGITS = frozenset("0123456789abcdef")


class ClaimError(Exception):
    """A refusal with a reason."""


def _recipe_path(d: str) -> str:
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe in {d!r}: expected {RECIPE} or {LEGACY_RECIPE}")


def _safe(base: str, name: str) -> str:
    """A recipe-declared path, confined to the claim: no absolute paths, no
    `..`/`.` components, no symlink component anywhere along the way."""
    if not name or not isinstance(name, str):
        raise ClaimError(f"refuses an empty or non-string path: {name!r}")
    if os.path.isabs(name) or "\x00" in name:
        raise ClaimError(f"refuses an absolute path: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", "..", ".") for p in parts):
        raise ClaimError(f"refuses a path that escapes the claim: {name!r}")

    base_real = os.path.realpath(base)
    cur = base_real
    for part in parts:
        candidate = os.path.join(cur, part)
        if os.path.islink(candidate):
            raise ClaimError(f"refuses a symlink component: {name!r}")
        cur = candidate

    resolved = os.path.normpath(os.path.join(base_real, *parts))
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ClaimError(f"refuses a path that escapes the claim: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    """Plain sha256 of a regular, singly-linked file's bytes."""
    if not os.path.isfile(path) or os.path.islink(path):
        raise ClaimError(f"refuses to hash a non-regular-file: {path!r}")
    if os.lstat(path).st_nlink != 1:
        raise ClaimError(f"refuses to hash a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _refuse_datetimes(obj) -> None:
    if isinstance(obj, (datetime.date, datetime.time)):
        raise ClaimError("TOML date/time values are refused in a recipe")
    if isinstance(obj, dict):
        for v in obj.values():
            _refuse_datetimes(v)
    elif isinstance(obj, list):
        for v in obj:
            _refuse_datetimes(v)


def _canonical_json(obj) -> str:
    """Sorted keys, default separators, ASCII escaping, exact-decimal
    integers, CPython float repr -- `json.dumps(obj, sort_keys=True)`."""
    _refuse_datetimes(obj)
    return json.dumps(obj, sort_keys=True)


def _hash_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_input_manifest(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        rest = rest.strip()
        if rest and len(head) == 64 and set(head) <= _HEXDIGITS:
            paths.append(rest)
        else:
            paths.append(line)
    return paths


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at `d`; refusals are `ClaimError`."""
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError(f"recipe {path!r} needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError(f"recipe {path!r}: [claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"recipe {path!r}: [claim] format must be a positive integer")

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError(f"recipe {path!r}: [[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"recipe {path!r}: every step must be a table")
        if step.get("kind") not in KINDS:
            raise ClaimError(
                f"recipe {path!r}: step kind must be one of {sorted(KINDS)}, "
                f"got {step.get('kind')!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError(f"recipe {path!r}: every step needs an output")
        _safe(d, output)
        if step.get("kind") == "gate":
            run = step.get("run")
            if not isinstance(run, str) or not run:
                raise ClaimError(f"recipe {path!r}: a gate step needs a run command")

    _inputs(parsed, d)
    return parsed


def _inputs(parsed: dict, d: str) -> list:
    """Pinned input paths: an explicit `inputs` list, or everything named by
    `inputs_manifest` (the manifest file itself, plus its entries)."""
    claim = parsed.get("claim", {})
    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        if not isinstance(manifest_name, str) or not manifest_name:
            raise ClaimError("[claim] inputs_manifest must be a string")
        manifest_path = _safe(d, manifest_name)
        entries = _read_input_manifest(manifest_path)
        for entry in entries:
            _safe(d, entry)
        return [manifest_name] + entries

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) and p for p in inputs):
        raise ClaimError("[claim] inputs must be a list of non-empty strings")
    for p in inputs:
        _safe(d, p)
    return list(inputs)


def _strip_guidance(step: dict) -> dict:
    stripped = dict(step)
    for key in GUIDANCE_KEYS:
        stripped.pop(key, None)
    return stripped


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root preimage: format >= 3 strips every
    step's guidance/request; format >= 4 additionally canonicalizes the step
    list to the lexicographic order of each step's own canonical JSON."""
    fmt = parsed.get("claim", {}).get("format", 1)
    steps = list(parsed.get("step", []))
    if fmt >= 3:
        steps = [_strip_guidance(s) for s in steps]
    if fmt >= 4:
        steps = sorted(steps, key=lambda s: json.dumps(s, sort_keys=True))
    out = dict(parsed)
    out["step"] = steps
    return out


def _parts(parsed: dict, d: str) -> dict:
    parts = {"digest": "sha256", "recipe": _canonical_json(_preimage_recipe(parsed))}

    for path in _inputs(parsed, d):
        parts["input:" + path] = _hash_file(_safe(d, path))

    for step in parsed.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_cls) == "generated":
            continue
        output = step["output"]
        parts["pinned:" + output] = _hash_file(_safe(d, output))

    return parts


def root(d: str) -> str:
    """The claim's identity: sha256 of the canonical parts map."""
    parsed = load_recipe(d)
    return _hash_str(_canonical_json(_parts(parsed, d)))


def _generated_outputs(parsed: dict) -> list:
    result = []
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        cls = step.get("class", "generated")
        if cls == "generated" and "from" not in step:
            result.append(step["output"])
    return result


def build_digest(d: str) -> str:
    """sha256 of the canonical, sorted list of [output, sha256] pairs over
    every generated output present on disk; the digest of the empty list
    when none exist."""
    parsed = load_recipe(d)
    pairs = []
    for output in _generated_outputs(parsed):
        path = _safe(d, output)
        if not os.path.exists(path):
            continue
        pairs.append([output, _hash_file(path)])
    pairs.sort()
    return _hash_str(_canonical_json(pairs))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="reticuli reference identity computation")
    ap.add_argument("verb", choices=["root", "build-digest"])
    ap.add_argument("claim", help="claim directory")
    args = ap.parse_args(argv)
    print(root(args.claim) if args.verb == "root" else build_digest(args.claim))
    return 0


if __name__ == "__main__":
    sys.exit(main())
