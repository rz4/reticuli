"""An independent implementation of the identity computation (spec/identity.md).

`root(d)` and `build_digest(d)` recompute a claim directory's identity and
build digest from the bytes present, without importing anything from
`reticuli.kernel` -- the two implementations are meant to agree by following
the same spec, not by sharing code (spec/vectors/README.md: "two
implementations, one answer").

A small CLI lets `spec/vectors/run.py` point at this module:

    python3 -m reticuli.reference root <claim-dir>
    python3 -m reticuli.reference digest <claim-dir>
"""
import hashlib
import json
import os
import sys
import tomllib

RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
DIGEST = "sha256"
GUIDANCE_KEYS = ("guidance", "request")
KINDS = ("produce", "gate")


class ClaimError(Exception):
    """A refusal with a reason -- the only error this module raises."""


def _recipe_path(d: str) -> str:
    for name in (RECIPE, LEGACY_RECIPE):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    raise ClaimError(f"no recipe ({RECIPE} or {LEGACY_RECIPE}) found in {d!r}")


def _validate(doc) -> None:
    if not isinstance(doc, dict):
        raise ClaimError("a recipe must be a table")
    claim = doc.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")
    if not isinstance(claim.get("name"), str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"[claim] format must be a positive integer: {fmt!r}")

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("every step must be a table")
        if step.get("kind") not in KINDS:
            raise ClaimError(f"refused step kind: {step.get('kind')!r}")
        output = step.get("output")
        if not isinstance(output, str) or not output:
            raise ClaimError("every step needs a string 'output'")
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("a gate step needs a string 'run'")


def load_recipe(d: str) -> dict:
    """Parse and validate `d`'s recipe; refusals, never a raw crash."""
    path = _recipe_path(d)
    try:
        with open(path, "rb") as f:
            doc = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    _validate(doc)
    return doc


def _safe(root_dir: str, name: str) -> str:
    """Resolve a recipe-declared name under `root_dir`, or refuse.

    Refuses an absolute or empty name, any `..` component, and any
    component that is itself a symlink -- a symlink could alias generated
    bytes as a pinned name (spec/identity.md).
    """
    if not name or os.path.isabs(name):
        raise ClaimError(f"refused path: {name!r}")
    parts = name.split("/")
    if any(p in ("", "..") for p in parts):
        raise ClaimError(f"refused path: {name!r}")
    root_real = os.path.realpath(root_dir)
    cur = root_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"refused symlink component: {name!r}")
    if cur != root_real and not cur.startswith(root_real + os.sep):
        raise ClaimError(f"refused path escape: {name!r}")
    return cur


def _hash_file(path: str) -> str:
    """A plain sha256 of a regular file's bytes; refuses anything that is
    not a single-hard-link regular file."""
    if os.path.islink(path) or not os.path.isfile(path):
        raise ClaimError(f"refused non-regular file: {path!r}")
    st = os.stat(path)
    if st.st_nlink != 1:
        raise ClaimError(f"refused hard-linked file: {path!r}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj) -> str:
    """The one serialization every preimage is built from: sorted keys,
    default separators, non-ASCII escaped."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True)


def _steps(recipe: dict) -> list:
    return recipe.get("step", [])


def _claim_format(recipe: dict) -> int:
    return recipe.get("claim", {}).get("format", 1)


def _read_input_manifest(path: str) -> list:
    """Paths named by an `inputs_manifest` file: one per line, `#`
    comments and blank lines ignored, an optional leading `<sha256> `
    stripped (spec/claim-format.md)."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    paths = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        if len(head) == 64 and rest.strip() and all(
            c in "0123456789abcdef" for c in head
        ):
            paths.append(rest.strip())
        else:
            paths.append(line)
    return paths


def _inputs(recipe: dict, d: str) -> list:
    """The claim's declared pinned inputs: the explicit list, an expanded
    `inputs_manifest` (itself a pinned input), and the `environment` file,
    where declared."""
    claim = recipe.get("claim", {})
    inputs = list(claim.get("inputs", []))

    manifest_name = claim.get("inputs_manifest")
    if manifest_name:
        inputs.append(manifest_name)
        inputs.extend(_read_input_manifest(_safe(d, manifest_name)))

    environment = claim.get("environment")
    if environment:
        inputs.append(environment)

    return inputs


def _preimage_recipe(recipe: dict) -> dict:
    """The recipe as it enters the root preimage: producer guidance
    stripped at format >= 3, the step list canonicalized to a set at
    format >= 4 (spec/identity.md)."""
    fmt = _claim_format(recipe)
    if fmt < 3 or "step" not in recipe:
        return recipe
    doc = dict(recipe)
    steps = [
        {k: v for k, v in step.items() if k not in GUIDANCE_KEYS}
        for step in recipe["step"]
    ]
    if fmt >= 4:
        steps = sorted(steps, key=_canonical_json)
    doc["step"] = steps
    return doc


def _parts(recipe: dict, d: str) -> dict:
    """The string-to-string map the root hashes."""
    parts = {"digest": DIGEST, "recipe": _canonical_json(_preimage_recipe(recipe))}
    for path in _inputs(recipe, d):
        parts["input:" + path] = _hash_file(_safe(d, path))
    for step in _steps(recipe):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            output = step["output"]
            parts["pinned:" + output] = _hash_file(_safe(d, output))
    return parts


def root(d: str) -> str:
    """The claim's identity: sha256 of the canonical preimage."""
    recipe = load_recipe(d)
    preimage = _canonical_json(_parts(recipe, d)).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def build_digest(d: str) -> str:
    """The digest a signature binds: sha256 over the sorted (path, hash)
    pairs of every present generated output that does not carry a `from`
    key; an absent output is omitted, never an error; the empty list's
    digest when none are present."""
    recipe = load_recipe(d)
    pairs = []
    for step in _steps(recipe):
        if step["kind"] != "produce" or "from" in step:
            continue
        if step.get("class", "generated") != "generated":
            continue
        path = _safe(d, step["output"])
        if not os.path.isfile(path):
            continue
        pairs.append([step["output"], _hash_file(path)])
    pairs.sort(key=lambda pair: pair[0])
    return hashlib.sha256(_canonical_json(pairs).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("root", "digest"):
        print("usage: python3 -m reticuli.reference root|digest <claim-dir>",
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
