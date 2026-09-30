"""reticuli.reference -- an independent implementation of spec/identity.md.

This module computes a claim's root and build digest straight from the
spec, without importing anything from reticuli.kernel or reticuli._kernel.
It exists so the conformance vectors under spec/vectors/ can pin one
answer that two independent implementations agree on (spec/vectors/README.md).

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>

Each prints a 64-character lowercase hex digest on stdout. Stdlib only.
"""
import hashlib
import json
import os
import stat
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST_ALGO = "sha256"
FORMAT = 3


class ReferenceError(Exception):
    """A refusal with a reason -- never a raw traceback."""


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_path(base: str, name: str) -> str:
    """Resolve a recipe-declared name to a path inside `base`, refusing
    an absolute path, an empty name, a '..' component, or any symlink
    component -- spec/identity.md, "File hashing rules"."""
    if not name:
        raise ReferenceError("empty name")
    if os.path.isabs(name):
        raise ReferenceError(f"absolute path refused: {name!r}")
    parts = name.split(os.sep)
    if ".." in parts:
        raise ReferenceError(f"'..' component refused: {name!r}")
    partial = base
    for part in parts:
        partial = os.path.join(partial, part)
        if os.path.islink(partial):
            raise ReferenceError(f"symlink component refused: {name!r}")
    if os.path.exists(partial):
        st = os.stat(partial, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode):
            raise ReferenceError(f"not a regular file: {name!r}")
        if st.st_nlink != 1:
            raise ReferenceError(f"file has more than one hard link: {name!r}")
    return partial


def _recipe_path(d: str) -> str:
    """The claim's recipe file, preferring `reticuli.toml` over the
    legacy `claim.toml` (spec/claim-format.md)."""
    for name in (RECIPE, LEGACY_RECIPE):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    raise ReferenceError(f"no recipe found in {d!r}")


def load_recipe(d: str) -> dict:
    """Parse and lightly validate `d`'s recipe."""
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ReferenceError(f"malformed recipe {path!r}: {exc}") from exc
    if not isinstance(parsed.get("claim"), dict):
        raise ReferenceError(f"recipe {path!r} is missing a [claim] table")
    name = parsed["claim"].get("name")
    if not isinstance(name, str):
        raise ReferenceError(f"[claim] name must be a string, got {name!r}")
    for step in parsed.get("step", []):
        if not isinstance(step, dict):
            raise ReferenceError(f"recipe {path!r} has a malformed step")
        if "kind" not in step or "output" not in step:
            raise ReferenceError(f"recipe {path!r} has a step with no kind/output")
    return parsed


def _claim_format(recipe: dict) -> int:
    fmt = recipe.get("claim", {}).get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ReferenceError(f"claim format must be a positive integer, got {fmt!r}")
    if fmt > FORMAT:
        raise ReferenceError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {FORMAT}); upgrade reticuli to read it"
        )
    return fmt


def _step_class(step: dict) -> str:
    cls = step.get("class")
    if cls is not None:
        return cls
    return "generated" if step.get("kind") == "produce" else "pinned"


def _preimage_recipe(recipe: dict) -> dict:
    """The recipe as it enters the root preimage: at format 3+, every
    step's `guidance`/`request` keys are stripped, since a hint for a
    rebuilder cannot decide acceptance (spec/identity.md, "Format 3")."""
    if _claim_format(recipe) < 3 or "step" not in recipe:
        return recipe
    stripped = dict(recipe)
    stripped["step"] = [
        {k: v for k, v in step.items() if k not in ("guidance", "request")}
        for step in recipe["step"]
    ]
    return stripped


def _json_default(obj):
    raise ReferenceError(
        f"cannot seal a value of type {type(obj).__name__} "
        "(TOML date/time values have no canonical JSON form)"
    )


def _canonical_json(obj) -> str:
    """sorted keys, default separators, ASCII-escaped -- spec/identity.md."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, default=_json_default)


def _parts(recipe: dict, d: str) -> dict:
    parts = {
        "digest": DIGEST_ALGO,
        "recipe": _canonical_json(_preimage_recipe(recipe)),
    }
    for path in recipe.get("claim", {}).get("inputs", []):
        resolved = _safe_path(d, path)
        try:
            parts[f"input:{path}"] = _hash_file(resolved)
        except OSError as exc:
            raise ReferenceError(f"missing declared input {path!r}: {exc}") from exc
    for step in recipe.get("step", []):
        if _step_class(step) == "generated":
            continue
        output = step["output"]
        resolved = _safe_path(d, output)
        try:
            parts[f"pinned:{output}"] = _hash_file(resolved)
        except OSError as exc:
            raise ReferenceError(f"missing pinned output {output!r}: {exc}") from exc
    return parts


def root(d: str) -> str:
    """The claim's identity: a SHA-256 hex digest over the canonical
    preimage (spec/identity.md)."""
    recipe = load_recipe(d)
    return hashlib.sha256(_canonical_json(_parts(recipe, d)).encode("utf-8")).hexdigest()


def build_digest(d: str) -> str:
    """The digest of the generated bytes present in `d`. Only `produce`
    steps of class `generated` with no `from` key contribute, and only
    when their output file is present on disk; an absent output is
    omitted, never an error. The digest of no entries is the digest of
    the empty list."""
    recipe = load_recipe(d)
    entries = []
    for step in recipe.get("step", []):
        if step.get("kind") != "produce" or _step_class(step) != "generated":
            continue
        if "from" in step:
            continue
        output = step["output"]
        path = _safe_path(d, output)
        if not os.path.isfile(path):
            continue
        entries.append([output, _hash_file(path)])
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
    except ReferenceError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
