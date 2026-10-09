"""A second, independent implementation of the identity computation
(`spec/identity.md`), used to cross-check `reticuli.kernel` and to drive
the conformance vectors in `spec/vectors/`.

Only the root and the build digest are implemented here -- the two values
the vectors pin. Stdlib only.
"""
import copy
import hashlib
import json
import os
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
FORMAT = 4

GENERATED_CLASSES = ("generated", "free")


class ReferenceError(Exception):
    """A refusal with a reason."""


def _safe(base: str, name: str) -> str:
    if not name:
        raise ReferenceError(f"empty path is refused: {name!r}")
    if os.path.isabs(name):
        raise ReferenceError(f"absolute path is refused: {name!r}")
    parts = name.split("/")
    for part in parts:
        if part in ("", ".."):
            raise ReferenceError(f"path escapes the claim: {name!r}")
    root = os.path.realpath(base)
    resolved = root
    for part in parts:
        candidate = os.path.join(resolved, part)
        if os.path.islink(candidate):
            raise ReferenceError(f"path crosses a symlink: {name!r}")
        resolved = candidate
    resolved = os.path.realpath(resolved)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise ReferenceError(f"path escapes the claim: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recipe_path(d: str) -> str:
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ReferenceError(f"no recipe in {d!r}: expected {RECIPE!r} or {LEGACY_RECIPE!r}")


def load_recipe(d: str) -> dict:
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ReferenceError(f"malformed recipe {path!r}: {e}") from e

    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ReferenceError("a recipe needs a [claim] table")
    claim = doc["claim"]

    name = claim.get("name")
    if not isinstance(name, str) or isinstance(name, bool):
        raise ReferenceError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ReferenceError("[claim] format must be a positive integer")
    if fmt > FORMAT:
        raise ReferenceError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ReferenceError("[claim] inputs must be a list of strings")
    for p in inputs:
        _safe(d, p)

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ReferenceError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ReferenceError("each step must be a table")
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise ReferenceError(f"step kind must be 'produce' or 'gate', got {kind!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ReferenceError(f"a {kind!r} step needs a string output")
        generated = kind == "produce" and step.get("class", "generated") in GENERATED_CLASSES
        if not generated:
            _safe(d, output)
        if kind == "gate":
            run_cmd = step.get("run")
            if not isinstance(run_cmd, str) or not run_cmd:
                raise ReferenceError("a gate step needs a string 'run' command")

    return doc


def _canonical_json(obj) -> str:
    """Sorted keys, default separators, ASCII escaping, exact-decimal
    integers, CPython-`repr` floats -- exactly `json.dumps(obj,
    sort_keys=True)` (`spec/identity.md`)."""
    return json.dumps(obj, sort_keys=True)


def _claim_format(doc: dict) -> int:
    return doc.get("claim", {}).get("format", 1)


def _preimage_recipe(doc: dict) -> dict:
    """The recipe exactly as it enters `parts["recipe"]`: guidance/request
    stripped from every step at format 3+, the (stripped) step list
    canonically re-sorted at format 4+ (`spec/identity.md`)."""
    fmt = _claim_format(doc)
    out = copy.deepcopy(doc)
    steps = out.get("step", [])
    if fmt >= 3:
        for step in steps:
            step.pop("guidance", None)
            step.pop("request", None)
    if fmt >= 4:
        steps = sorted(steps, key=_canonical_json)
        out["step"] = steps
    return out


def _inputs(doc: dict) -> list:
    return list(doc.get("claim", {}).get("inputs", []))


def _parts(doc: dict, d: str) -> dict:
    parts = {
        "digest": DIGEST,
        "recipe": _canonical_json(_preimage_recipe(doc)),
    }
    for path in _inputs(doc):
        parts["input:" + path] = _hash_file(_safe(d, path))
    for step in doc.get("step", []):
        kind = step["kind"]
        cls = step.get("class")
        if kind == "produce" and (cls if cls is not None else "generated") in GENERATED_CLASSES:
            continue
        path = step["output"]
        parts["pinned:" + path] = _hash_file(_safe(d, path))
    return parts


def root(d: str) -> str:
    """The claim's identity (`spec/identity.md`)."""
    doc = load_recipe(d)
    preimage = _canonical_json(_parts(doc, d))
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def build_digest(d: str) -> str:
    """The digest of the generated bytes present now (`spec/identity.md`):
    one `[path, sha256]` pair per produce step whose class is generated,
    excluding any step carrying `from` and any output absent on disk."""
    doc = load_recipe(d)
    entries = []
    for step in doc.get("step", []):
        if step.get("kind") != "produce":
            continue
        cls = step.get("class")
        if (cls if cls is not None else "generated") not in GENERATED_CLASSES:
            continue
        if "from" in step:
            continue
        path = step["output"]
        full = _safe(d, path)
        if not os.path.isfile(full):
            continue
        entries.append([path, _hash_file(full)])
    entries.sort(key=lambda e: e[0])
    return hashlib.sha256(_canonical_json(entries).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: reticuli.reference {root|digest} <claim-dir>", file=sys.stderr)
        return 2
    verb, d = argv
    try:
        value = root(d) if verb == "root" else build_digest(d)
    except ReferenceError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
