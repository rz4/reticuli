"""Identity: the root hash and the build digest (spec/identity.md).

The root is a SHA-256 digest over a string-to-string map built from the
claim's recipe (stripped of producer guidance at format >= 3, with the
step list canonicalized as a set at format >= 4), the bytes of every
pinned input, and the bytes of every non-generated step output. The
build digest is a SHA-256 digest over the generated outputs actually
present on disk, excluding any output a `from` key attributes to
another claim.
"""
import hashlib
import json
import os

from reticuli._kernel import core, recipe


def _claim_format(parsed: dict) -> int:
    """The claim's declared format; absent means 1 (spec/claim-format.md)."""
    return parsed.get("claim", {}).get("format", 1)


def _canonical_json(obj) -> str:
    """`json.dumps(obj, sort_keys=True)` with every other argument at its
    default: default separators, non-ASCII escaped, arbitrary-precision
    integers, CPython's shortest round-trip float repr (spec/identity.md).

    A TOML date or time value has no canonical JSON form and is refused
    rather than silently dropped or stringified.
    """
    def _refuse(o):
        raise core.ClaimError(
            f"refused: a {type(o).__name__} value has no canonical form "
            "and cannot enter a preimage (TOML date/time values are refused)"
        )
    return json.dumps(obj, sort_keys=True, default=_refuse)


def _effective_class(step: dict) -> str:
    """A `produce` step defaults to `generated`; any other step output
    defaults to `pinned` (spec/claim-format.md)."""
    cls = step.get("class")
    if cls is not None:
        return cls
    return "generated" if step.get("kind") == "produce" else "pinned"


def _strip_guidance(step: dict) -> dict:
    """A step with every guidance key (`guidance`, `request`) removed."""
    return {k: v for k, v in step.items() if k not in core.GUIDANCE_KEYS}


def _preimage_recipe(parsed: dict) -> dict:
    """The recipe exactly as it enters the root preimage (spec/identity.md).

    At format 1-2 this is the parsed recipe unchanged. At format >= 3
    every step's guidance keys are stripped. At format >= 4 the
    (guidance-stripped) step list is additionally canonicalized as a
    set: sorted by each step's own canonical JSON encoding, so the
    file order a particular authoring tool chose cannot move the root.
    """
    fmt = _claim_format(parsed)
    if fmt < 3:
        return parsed
    steps = [_strip_guidance(s) for s in parsed.get("step", [])]
    if fmt >= 4:
        steps.sort(key=_canonical_json)
    out = dict(parsed)
    out["step"] = steps
    return out


def _parts(parsed: dict, d: str) -> dict:
    """The string-to-string map the root hashes (spec/identity.md)."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical_json(_preimage_recipe(parsed)),
    }
    for path in recipe._inputs(d, parsed):
        parts["input:" + path] = core._hash_file(core._safe(d, path))
    for step in parsed.get("step", []):
        if _effective_class(step) != "generated":
            parts["pinned:" + step["output"]] = core._hash_file(
                core._safe(d, step["output"])
            )
    return parts


def root(parsed: dict, d: str) -> str:
    """The claim's identity (spec/identity.md)."""
    preimage = _canonical_json(_parts(parsed, d)).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()


def build_digest(d: str) -> str:
    """The digest a signature binds: a SHA-256 over the generated outputs
    present on disk, excluding any output a `from` key names as supplied
    by another claim; the digest of the empty list when none exist
    (spec/identity.md).
    """
    parsed = recipe.load_recipe(d)
    pairs = []
    for step in parsed.get("step", []):
        if _effective_class(step) != "generated" or step.get("from") is not None:
            continue
        path = core._safe(d, step["output"])
        if os.path.isfile(path):
            pairs.append([step["output"], core._hash_file(path)])
    pairs.sort()
    preimage = _canonical_json(pairs).encode("ascii")
    return hashlib.sha256(preimage).hexdigest()
