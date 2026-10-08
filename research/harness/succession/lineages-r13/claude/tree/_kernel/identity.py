"""Identity: the root hash and the build digest (spec/identity.md).

`root` hashes what a claim *is* — its parsed recipe, its pinned inputs, its
non-generated step outputs — never the bytes of a `generated` output.
`build_digest` is the opposite cut: a digest over exactly the generated
bytes present, the digest of the empty list when none exist. Both are
`sha256(canonical_json(...))`, where `canonical_json` is
`json.dumps(x, sort_keys=True)` left at every other default: sorted keys,
default (non-compact) separators, non-ASCII escaped as `\\uXXXX`, integers in
exact decimal, floats as CPython's `repr`. TOML date/time values have no
such form and are refused.
"""
import hashlib
import json
import os

from . import core
from . import recipe as recipe_mod


def _claim_format(parsed: dict) -> int:
    """The claim's declared format; absent means 1."""
    return parsed.get("claim", {}).get("format", 1)


def _refuse_datetimes(obj) -> None:
    import datetime

    if isinstance(obj, (datetime.date, datetime.time)):
        raise core.ClaimError("TOML date/time values are refused in a recipe")
    if isinstance(obj, dict):
        for v in obj.values():
            _refuse_datetimes(v)
    elif isinstance(obj, list):
        for v in obj:
            _refuse_datetimes(v)


def _canonical_json(obj) -> str:
    """The canonical serialization: sorted keys, default separators, ASCII
    escaping, arbitrary-precision integers, CPython float repr."""
    _refuse_datetimes(obj)
    return json.dumps(obj, sort_keys=True)


def _hash_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _strip_guidance(step: dict) -> dict:
    stripped = dict(step)
    for key in core.GUIDANCE_KEYS:
        stripped.pop(key, None)
    return stripped


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root preimage. Format 3 strips every
    step's `guidance`/`request`; format 4 additionally canonicalizes the
    step list to the lexicographic order of each step's own canonical JSON.
    Formats 1-2 leave the recipe exactly as parsed."""
    fmt = _claim_format(parsed)
    steps = list(parsed.get("step", []))
    if fmt >= 3:
        steps = [_strip_guidance(s) for s in steps]
    if fmt >= 4:
        steps = sorted(steps, key=lambda s: json.dumps(s, sort_keys=True))
    out = dict(parsed)
    out["step"] = steps
    return out


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map whose canonical serialization is hashed to
    produce the root: the algorithm, the preimage recipe, every pinned
    input, and every non-generated step output."""
    parts = {"digest": core.DIGEST, "recipe": _canonical_json(_preimage_recipe(parsed))}

    for path in recipe_mod._inputs(parsed, d):
        parts["input:" + path] = core._hash_file(core._safe(d, path))

    for step in recipe_mod._steps(parsed):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_cls) == "generated":
            continue
        output = step["output"]
        parts["pinned:" + output] = core._hash_file(core._safe(d, output))

    return parts


def root(recipe: dict, d: str) -> str:
    """The claim's identity: sha256 of the canonical parts map."""
    return _hash_str(_canonical_json(_parts(recipe, d)))


def build_digest(d: str) -> str:
    """The digest a signature binds: sha256 of the canonical, sorted list of
    [output, sha256] pairs over every `generated` output present on disk
    (a `from` output is excluded; an absent one is omitted); the digest of
    the empty list when none exist."""
    parsed = recipe_mod.load_recipe(d)
    pairs = []
    for output in recipe_mod.generated_outputs(parsed):
        path = core._safe(d, output)
        if not os.path.exists(path):
            continue
        pairs.append([output, core._hash_file(path)])
    pairs.sort()
    return _hash_str(_canonical_json(pairs))
