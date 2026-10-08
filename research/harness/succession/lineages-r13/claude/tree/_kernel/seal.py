"""Freezing identity, and confirming it (spec/claim-format.md, spec/identity.md).

`seal` computes a claim's root from the bytes present and writes it to
`.reticuli/manifest.json`. `verify` recomputes the root from whatever bytes
are present now and reports whether they still hash to the sealed value --
identity only, no gate is executed. The manifest also carries the parts map
`seal` hashed, so a mismatch can be explained in terms of which pinned input
or step output moved, not just that something did.
"""
import json
import os

from . import core
from . import identity
from . import recipe as recipe_mod


def seal(d: str) -> dict:
    """Freeze a workspace into a claim: compute the root, write the manifest."""
    parsed = recipe_mod.load_recipe(d)
    parts = identity._parts(parsed, d)
    r = identity._hash_str(identity._canonical_json(parts))
    manifest = {"name": parsed["claim"]["name"], "root": r, "parts": parts}
    manifest_path = os.path.join(d, core.MANIFEST)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    core._write_json(manifest_path, manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Read back `.reticuli/manifest.json`; malformed bytes are refused."""
    path = os.path.join(d, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except OSError as exc:
        raise core.ClaimError(f"cannot read manifest {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise core.ClaimError(f"malformed manifest {path!r}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise core.ClaimError(f"malformed manifest {path!r}: not a JSON object")
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        raise core.ClaimError(f"malformed manifest {path!r}: missing name")
    root = manifest.get("root")
    if not isinstance(root, str) or len(root) != 64:
        raise core.ClaimError(f"malformed manifest {path!r}: root must be 64 hex characters")
    return manifest


def _changed_parts(old_parts: dict, new_parts: dict) -> list:
    """The parts keys (`input:`/`pinned:` paths) whose hash differs between
    a sealed parts map and a freshly recomputed one -- what moved the root."""
    keys = set(old_parts) | set(new_parts)
    return sorted(k for k in keys if old_parts.get(k) != new_parts.get(k))


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the
    sealed manifest -- identity only, no gate is executed."""
    manifest = read_manifest(d)
    parsed = recipe_mod.load_recipe(d)
    new_parts = identity._parts(parsed, d)
    recomputed = identity._hash_str(identity._canonical_json(new_parts))
    sealed_root = manifest["root"]
    ok = recomputed == sealed_root

    result = {
        "ok": ok,
        "root": sealed_root,
        "recomputed": recomputed,
        "name": manifest["name"],
    }
    if not ok:
        old_parts = manifest.get("parts")
        if isinstance(old_parts, dict):
            result["changed"] = _changed_parts(old_parts, new_parts)
    return result
