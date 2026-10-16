"""Kernel identity: the root hash and the build digest (spec/identity.md)."""
import copy
import hashlib
import json
import os

from . import core, recipe as _recipe
from .core import ClaimError


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _claim_format(rec: dict) -> int:
    claim = rec.get("claim", {}) if isinstance(rec, dict) else {}
    fmt = claim.get("format", 1) if isinstance(claim, dict) else 1
    return fmt if isinstance(fmt, int) and not isinstance(fmt, bool) else 1


def _preimage_recipe(rec: dict) -> dict:
    """The recipe as it enters the preimage, per its declared format."""
    fmt = _claim_format(rec)
    if fmt < 3:
        return rec
    out = copy.deepcopy(rec)
    steps = out.get("step")
    if isinstance(steps, list):
        stripped = []
        for s in steps:
            if isinstance(s, dict):
                s = {k: v for k, v in s.items() if k not in core.GUIDANCE_KEYS}
            stripped.append(s)
        if fmt >= 4:
            stripped.sort(key=lambda s: json.dumps(s, sort_keys=True))
        out["step"] = stripped
    return out


def _parts(rec: dict, d: str) -> dict:
    parts = {"digest": core.DIGEST,
             "recipe": _canonical(_preimage_recipe(rec))}
    for p in _recipe._inputs(d, rec):
        parts["input:" + p] = core._hash_file(core._safe(d, p))
    for s in _recipe._steps(rec):
        if _recipe._class(s) != "generated":
            out = s["output"]
            parts["pinned:" + out] = core._hash_file(core._safe(d, out))
    return parts


def root(rec: dict, d: str) -> str:
    return _sha(_canonical(_parts(rec, d)))


def build_digest(d: str) -> str:
    rec = _recipe.load_recipe(d)
    seen = set()
    entries = []
    for out in _recipe.generated_outputs(rec):
        if out in seen:
            continue
        seen.add(out)
        full = core._safe(d, out)
        if not os.path.lexists(full):
            continue
        entries.append([out, core._hash_file(full)])
    entries.sort()
    return _sha(_canonical(entries))
