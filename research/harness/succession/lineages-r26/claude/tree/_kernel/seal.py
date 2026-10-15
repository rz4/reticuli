"""Sealing and verifying a claim's identity.

`seal` computes the root from the bytes present and writes it to
`.reticuli/manifest.json`, alongside the preimage parts the root was built
from -- residue kept only so a later `verify` can report *which* entry moved,
never consulted to decide identity itself. `verify` recomputes the root from
the bytes present and compares it with the sealed manifest: identity only,
no gate is ever run here (`spec/verification.md` -- that is `audit`'s job).
Editing a `generated` output never touches the preimage, so the root is
unchanged; editing a pinned input or input changes an `input:`/`pinned:`
entry, and the root moves with it.

Stdlib only.
"""
import hashlib
import json
import os

from . import core, identity, recipe
from .core import ClaimError


def read_manifest(d: str) -> dict:
    """The sealed manifest at claim directory `d`: at least `{name, root}`."""
    path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(path):
        raise ClaimError(f"no sealed manifest at {path!r}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ClaimError(f"malformed manifest {path!r}: {e}") from e
    if not isinstance(manifest, dict):
        raise ClaimError(f"malformed manifest {path!r}: not an object")
    if not isinstance(manifest.get("name"), str):
        raise ClaimError(f"malformed manifest {path!r}: missing name")
    root = manifest.get("root")
    if not isinstance(root, str) or len(root) != 64:
        raise ClaimError(f"malformed manifest {path!r}: missing root")
    return manifest


def _root_from_parts(parts: dict) -> str:
    return hashlib.sha256(identity._canonical_json(parts).encode("utf-8")).hexdigest()


def seal(d: str) -> dict:
    """Freeze a workspace into a claim: compute the root, write the manifest."""
    parsed = recipe.load_recipe(d)
    name = parsed["claim"]["name"]
    parts = identity._parts(parsed, d)
    manifest = {"name": name, "root": _root_from_parts(parts), "parts": parts}
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


def _changed_parts(sealed_parts: dict, current_parts: dict) -> list:
    """Which preimage entries differ between a sealed manifest and the bytes present now."""
    keys = set(sealed_parts) | set(current_parts)
    return sorted(k for k in keys if sealed_parts.get(k) != current_parts.get(k))


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the seal."""
    manifest = read_manifest(d)
    parsed = recipe.load_recipe(d)
    try:
        current_parts = identity._parts(parsed, d)
        recomputed = _root_from_parts(current_parts)
    except ClaimError:
        current_parts, recomputed = {}, None
    ok = recomputed is not None and recomputed == manifest["root"]
    result = {
        "ok": ok,
        "name": manifest["name"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
    if not ok:
        result["changed"] = _changed_parts(manifest.get("parts", {}), current_parts)
    return result
