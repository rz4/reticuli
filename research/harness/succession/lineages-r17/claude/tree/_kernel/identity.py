"""Identity: the root hash and the build digest (`spec/identity.md`).

`root(recipe, d)` hashes what a claim *is* -- its parsed recipe (format-3
guidance stripped, format-4 steps canonicalized) plus the bytes of every
pinned input and every non-generated step output. `build_digest(d)` hashes
what a claim *currently holds* -- the bytes of its generated outputs, the
digest a signature binds.

Both reduce to one move: serialize a Python value with `_claim_format`'s
canonical rule (`json.dumps(x, sort_keys=True)`, stdlib default separators
and ASCII escaping) and sha256 the UTF-8 bytes. Stdlib only.
"""
import hashlib
import json
import os

from . import core, recipe
from .core import ClaimError


def _claim_format(parsed: dict) -> int:
    """The claim's declared format; absent means 1 (`spec/claim-format.md`)."""
    return parsed.get("claim", {}).get("format", 1)


def _canonical_json(obj) -> str:
    """Sorted keys, default (non-compact) separators, ASCII-escaped."""
    try:
        return json.dumps(obj, sort_keys=True)
    except TypeError as e:
        raise ClaimError(f"recipe value has no canonical JSON form: {e}") from e


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe as it enters the root preimage, per the claim's format.

    Format 1/2 serialize the parsed recipe untouched. Format 3 strips every
    step's `guidance`/`request` key -- a producer hint, never a criterion.
    Format 4 additionally sorts the step list by each step's own canonical
    JSON encoding, so the file order (authoring form) cannot move the root.
    """
    fmt = _claim_format(parsed)
    if fmt < 3 or "step" not in parsed:
        return parsed
    steps = [
        {k: v for k, v in step.items() if k not in core.GUIDANCE_KEYS}
        for step in parsed["step"]
    ]
    if fmt >= 4:
        steps = sorted(steps, key=lambda s: json.dumps(s, sort_keys=True))
    result = dict(parsed)
    result["step"] = steps
    return result


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map the root digests (`spec/identity.md`)."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical_json(_preimage_recipe(parsed)),
    }
    for path in recipe._inputs(d, parsed):
        parts[f"input:{path}"] = core._hash_file(core._safe(d, path))
    for step in recipe._steps(parsed):
        cls = step.get("class", recipe._default_class(step))
        if cls != "generated":
            output = step["output"]
            parts[f"pinned:{output}"] = core._hash_file(core._safe(d, output))
    return parts


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def root(parsed: dict, d: str) -> str:
    """The claim's identity: sha256 of the canonical `parts` map."""
    return _sha256_text(_canonical_json(_parts(parsed, d)))


def build_digest(d: str) -> str:
    """Digest over concrete bytes, generated outputs included.

    Every `produce` step whose (possibly defaulted) class is `generated`,
    has no `from`, and whose output exists on disk, contributes
    `[output, sha256(bytes)]`; the list is sorted by output path and hashed
    canonically. An absent generated output is omitted, never refused --
    build_digest measures what is present. No qualifying output yields the
    empty list.
    """
    parsed = recipe.load_recipe(d)
    pairs = []
    for step in recipe.produces(parsed):
        if step.get("from") is not None:
            continue
        if step.get("class", recipe._default_class(step)) != "generated":
            continue
        output = step["output"]
        path = core._safe(d, output)
        if not os.path.isfile(path):
            continue
        pairs.append([output, core._hash_file(path)])
    pairs.sort(key=lambda pair: pair[0])
    return _sha256_text(_canonical_json(pairs))
