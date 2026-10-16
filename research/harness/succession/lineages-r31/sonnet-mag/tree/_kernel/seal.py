"""Kernel seal: record the root onto the manifest, and verify it again."""
import json
import os

from . import core, identity, recipe as _recipe
from .core import ClaimError


def _manifest_path(d: str) -> str:
    return core._safe(d, core.MANIFEST)


def seal(d: str) -> dict:
    """Compute the root of claim dir `d` and write `.reticuli/manifest.json`."""
    rec = _recipe.load_recipe(d)
    parts = identity._parts(rec, d)
    root = identity._sha(identity._canonical(parts))
    manifest = {"name": rec["claim"]["name"], "root": root,
                "parts": {k: v for k, v in parts.items() if k != "recipe"}}
    core._write_json(_manifest_path(d), manifest)
    return {"name": manifest["name"], "root": root}


def read_manifest(d: str) -> dict:
    """The sealed manifest; malformed bytes are refused."""
    path = _manifest_path(d)
    try:
        with open(path, "rb") as f:
            m = json.loads(f.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as e:
        raise ClaimError(f"cannot read manifest: {e}")
    if not isinstance(m, dict):
        raise ClaimError("malformed manifest: not an object")
    name, root = m.get("name"), m.get("root")
    if not isinstance(name, str) or not name:
        raise ClaimError("malformed manifest: name")
    if (not isinstance(root, str) or len(root) != 64
            or any(c not in "0123456789abcdef" for c in root)):
        raise ClaimError("malformed manifest: root")
    return m


def _changed_parts(d: str) -> list:
    """Names of pinned parts whose current hashes differ from the sealed ones."""
    m = read_manifest(d)
    sealed = m.get("parts")
    if not isinstance(sealed, dict):
        return []
    rec = _recipe.load_recipe(d)
    now = {k: v for k, v in identity._parts(rec, d).items() if k != "recipe"}
    keys = set(sealed) | set(now)
    return sorted(k for k in keys if sealed.get(k) != now.get(k))


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare to the sealed one."""
    m = read_manifest(d)
    rec = _recipe.load_recipe(d)
    try:
        recomputed = identity.root(rec, d)
    except ClaimError as e:
        return {"ok": False, "root": m["root"], "recomputed": None,
                "name": m["name"], "reason": str(e)}
    return {"ok": recomputed == m["root"], "root": m["root"],
            "recomputed": recomputed, "name": m["name"]}
