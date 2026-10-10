"""Independent reference implementation of the identity computation.

Computes a claim's root and build digest exactly as spec/identity.md
describes them. Deliberately does not import `reticuli.kernel` or
`reticuli._kernel`: the conformance vectors require two implementations
that agree because they both follow the spec, not because they share code,
so this module is written from the spec alone.

    python3 -m reticuli.reference root <claim-directory>
    python3 -m reticuli.reference digest <claim-directory>
"""
import hashlib
import json
import os
import stat
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
GUIDANCE_KEYS = ("guidance", "request")


class ReferenceError(Exception):
    """A refusal with a reason."""


def _recipe_path(d: str) -> str:
    """The recipe file's path under `d`, preferring `reticuli.toml` over the
    legacy `claim.toml` -- the filename itself is outside the root."""
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ReferenceError(f"no recipe found in {d!r}: expected {RECIPE} or {LEGACY_RECIPE}")


def load_recipe(d: str) -> dict:
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ReferenceError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise ReferenceError(f"cannot read recipe {path!r}: {exc}") from exc


def _safe_path(d: str, name: str) -> str:
    """Resolve a recipe-declared name under `d`, or refuse: no absolute or
    empty name, no `.`/`..` component, no component that is a symlink --
    even one whose target stays inside the claim (spec/identity.md)."""
    if not isinstance(name, str) or not name:
        raise ReferenceError(f"refuses an empty path: {name!r}")
    if os.path.isabs(name):
        raise ReferenceError(f"refuses an absolute path: {name!r}")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ReferenceError(f"path escapes the claim: {name!r}")
    resolved = os.path.realpath(d)
    for part in parts:
        resolved = os.path.join(resolved, part)
        if os.path.islink(resolved):
            raise ReferenceError(f"path crosses a symlink: {name!r}")
    return resolved


def _hash_file(path: str) -> str:
    """A plain sha256 of a file's content; refuses anything that is not a
    regular, singly-linked file (spec/identity.md)."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise ReferenceError(f"refuses a symlink: {path!r}")
    if not stat.S_ISREG(st.st_mode):
        raise ReferenceError(f"refuses a non-regular file: {path!r}")
    if st.st_nlink != 1:
        raise ReferenceError(f"refuses a hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj) -> str:
    """`json.dumps(obj, sort_keys=True)` at its defaults: sorted keys,
    default separators, ASCII-escaped non-ASCII, exact-decimal integers,
    repr-shortest floats -- exactly spec/identity.md's rule. A TOML
    date/time value has no canonical JSON form and is refused here."""
    try:
        return json.dumps(obj, sort_keys=True)
    except TypeError as exc:
        raise ReferenceError(
            f"value has no canonical JSON form (TOML date/time values are "
            f"refused at sealing): {exc}"
        ) from exc


def _claim_format(recipe: dict) -> int:
    """The claim's declared format; absent means 1 (spec/claim-format.md)."""
    fmt = recipe.get("claim", {}).get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ReferenceError(f"[claim] format must be a positive integer, got {fmt!r}")
    return fmt


def _preimage_recipe(recipe: dict) -> dict:
    """The recipe exactly as it enters the root preimage: at format >= 3
    every step's `guidance`/`request` key is stripped (it cannot decide
    acceptance, so it is not identity-bearing); at format >= 4 the stripped
    steps are reordered into the lexicographic order of their own canonical
    JSON encodings, so the step list is a set rather than authoring-order
    text (spec/identity.md)."""
    fmt = _claim_format(recipe)
    steps = [dict(s) for s in recipe.get("step", [])]
    if fmt >= 3:
        steps = [{k: v for k, v in s.items() if k not in GUIDANCE_KEYS} for s in steps]
    if fmt >= 4:
        steps.sort(key=_canonical_json)
    preimage = dict(recipe)
    if "step" in recipe or steps:
        preimage["step"] = steps
    return preimage


def _read_input_manifest(path: str) -> list:
    """A format-2 inputs manifest: one path per line, an optional
    `<sha256>  <path>` prefix, blank lines and `#` comments ignored."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ReferenceError(f"cannot read inputs manifest {path!r}: {exc}") from exc
    hexdigits = frozenset("0123456789abcdef")
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        rest = rest.strip()
        if rest and len(head) == 64 and all(c in hexdigits for c in head):
            entries.append(rest)
        else:
            entries.append(line)
    return entries


def _inputs(recipe: dict, d: str) -> list:
    """Every pinned-input path a root hashes as `input:path`: the declared
    `inputs` list, a format-2 `inputs_manifest`'s own bytes plus every path
    it names, and a declared `environment` file."""
    claim = recipe.get("claim", {})
    inputs = list(claim.get("inputs", []))

    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        manifest_path = _safe_path(d, manifest_name)
        if not os.path.isfile(manifest_path):
            raise ReferenceError(f"inputs_manifest names a file that is gone: {manifest_name!r}")
        inputs.append(manifest_name)
        for entry in _read_input_manifest(manifest_path):
            entry_path = _safe_path(d, entry)
            if not os.path.isfile(entry_path):
                raise ReferenceError(f"inputs_manifest names a file that is gone: {entry!r}")
            inputs.append(entry)

    environment = claim.get("environment")
    if environment is not None:
        inputs.append(environment)

    return inputs


def _step_class(step: dict) -> str:
    kind = step.get("kind")
    return step.get("class", "generated" if kind == "produce" else "pinned")


def _parts(recipe: dict, d: str) -> dict:
    """The string-to-string map the root hashes (spec/identity.md)."""
    parts = {
        "digest": "sha256",
        "recipe": _canonical_json(_preimage_recipe(recipe)),
    }
    for path in _inputs(recipe, d):
        parts["input:" + path] = _hash_file(_safe_path(d, path))
    for step in recipe.get("step", []):
        if _step_class(step) == "generated":
            continue
        output = step.get("output")
        if not output:
            continue
        parts["pinned:" + output] = _hash_file(_safe_path(d, output))
    return parts


def root(d: str) -> str:
    """The claim's identity: sha256 of the canonical `parts` map."""
    recipe = load_recipe(d)
    return hashlib.sha256(_canonical_json(_parts(recipe, d)).encode("utf-8")).hexdigest()


def build_digest(d: str) -> str:
    """The digest a signature binds: sha256 over the sorted `[output,
    sha256]` pairs of every present generated-class produce step, excluding
    one carrying a `from` key; the empty list when none are present."""
    recipe = load_recipe(d)
    pairs = []
    for step in recipe.get("step", []):
        if step.get("kind") != "produce":
            continue
        if _step_class(step) != "generated":
            continue
        if "from" in step:
            continue
        output = step.get("output")
        path = _safe_path(d, output)
        if not os.path.isfile(path):
            continue
        pairs.append([output, _hash_file(path)])
    pairs.sort(key=lambda pair: pair[0])
    return hashlib.sha256(_canonical_json(pairs).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference {root|digest} <claim-directory>",
              file=sys.stderr)
        return 2
    verb, directory = argv
    try:
        print(root(directory) if verb == "root" else build_digest(directory))
    except ReferenceError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
