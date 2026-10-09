"""Freezing identity, and confirming it (`spec/verification.md`).

`seal(d)` computes the root (`identity.root`) from the bytes present and
writes it onto `.reticuli/manifest.json`. `verify(d)` recomputes the root
from the bytes present now and compares it with what was sealed -- identity
only, no gate is executed. `read_manifest(d)` parses that manifest back,
refusing malformed bytes rather than crashing. `_changed_parts` is the
diagnostic behind a mismatch: which single preimage component (which input,
which pinned output, or the recipe itself) moved since sealing.

Stdlib only.
"""
import json
import os

from . import core, identity, recipe
from .core import ClaimError


def seal(d: str, **kwargs) -> dict:
    """Freeze a workspace into a claim: compute the root, write the manifest."""
    parsed = recipe.load_recipe(d)
    name = parsed["claim"]["name"]
    parts = identity._parts(parsed, d)
    root = identity._sha256_text(identity._canonical_json(parts))
    manifest = {"name": name, "root": root, "parts": parts}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Parse `.reticuli/manifest.json`; malformed bytes are refused."""
    path = os.path.join(d, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError as e:
        raise ClaimError(f"no sealed manifest in {d!r}; run seal first") from e
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed manifest {path!r}: {e}") from e

    if not isinstance(doc, dict):
        raise ClaimError(f"malformed manifest {path!r}: not a JSON object")
    name = doc.get("name")
    root = doc.get("root")
    if not isinstance(name, str):
        raise ClaimError(f"malformed manifest {path!r}: name must be a string")
    if not isinstance(root, str) or len(root) != 64:
        raise ClaimError(
            f"malformed manifest {path!r}: root must be 64 hex characters")
    return doc


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare with the seal.

    Identity only -- no gate is executed. `root` is what was sealed;
    `recomputed` is what the present bytes hash to now; `ok` is whether they
    match.
    """
    manifest = read_manifest(d)
    parsed = recipe.load_recipe(d)
    recomputed = identity.root(parsed, d)
    return {"ok": recomputed == manifest["root"],
            "root": manifest["root"],
            "recomputed": recomputed}


def _changed_parts(d: str) -> dict:
    """Which preimage parts differ between the sealed manifest and now.

    Diagnostic only -- not part of the root computation itself. Returns the
    keys added, removed, or changed in the `identity._parts` map (each key
    names either `"recipe"`, an `"input:<path>"`, or a `"pinned:<path>"`).
    """
    manifest = read_manifest(d)
    sealed_parts = manifest.get("parts")
    if not isinstance(sealed_parts, dict):
        raise ClaimError(
            f"sealed manifest in {d!r} carries no parts to diff against")
    parsed = recipe.load_recipe(d)
    current_parts = identity._parts(parsed, d)

    sealed_keys = set(sealed_parts)
    current_keys = set(current_parts)
    return {
        "added": sorted(current_keys - sealed_keys),
        "removed": sorted(sealed_keys - current_keys),
        "changed": sorted(
            k for k in sealed_keys & current_keys
            if sealed_parts[k] != current_parts[k]),
    }
