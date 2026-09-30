"""Seal and verify: freezing identity, and confirming it (spec/verification.md).

`seal` computes a claim's root (spec/identity.md) and writes it, with the
claim's name, to `.reticuli/manifest.json` -- the store's pure-identity
record. `verify` recomputes the root from the bytes present and compares it
with the sealed manifest; it runs no gate, so it answers "is this still the
same claim?" in milliseconds, not "does it currently pass".
"""
import os

from . import core, identity, recipe
from .core import ClaimError


def _changed_parts(old: dict, new: dict) -> list:
    """Sorted keys where two `parts` maps (spec/identity.md) disagree.

    A key present in only one map, or whose value differs, is "changed";
    used to explain a root mismatch rather than merely report one.
    """
    keys = set(old) | set(new)
    return sorted(k for k in keys if old.get(k) != new.get(k))


def seal(d: str) -> dict:
    """Freeze `d`: compute the root, write `.reticuli/manifest.json`.

    Returns the manifest written: `{"name": ..., "root": ...}`.
    """
    parsed = recipe.load_recipe(d)
    name = parsed["claim"]["name"]
    computed_root = identity.root(parsed, d)
    manifest = {"name": name, "root": computed_root}

    store = os.path.join(d, core.STORE)
    os.makedirs(store, exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Read and validate `.reticuli/manifest.json`: `{name, root}`.

    Refuses (`ClaimError`) a missing file, invalid JSON, a document that is
    not an object, a missing or non-string `name`, or a `root` that is not
    64 lowercase-hex characters.
    """
    import json

    path = os.path.join(d, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"no manifest at {path!r}: {e}") from e

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed manifest {path!r}: {e}") from e

    if not isinstance(doc, dict):
        raise ClaimError(f"manifest {path!r} must be a JSON object")

    name = doc.get("name")
    if not isinstance(name, str):
        raise ClaimError(f"manifest {path!r} name must be a string")

    root = doc.get("root")
    if not isinstance(root, str) or len(root) != 64 or any(
        c not in "0123456789abcdef" for c in root
    ):
        raise ClaimError(f"manifest {path!r} root must be 64 lowercase-hex characters")

    return doc


def verify(d: str) -> dict:
    """Recompute the root from the bytes present; compare with the sealed one.

    Identity only -- no gate is executed (spec/verification.md). Returns
    `{"ok": bool, "root": <sealed root>, "recomputed": <root now>}`.
    """
    manifest = read_manifest(d)
    parsed = recipe.load_recipe(d)
    recomputed = identity.root(parsed, d)
    sealed_root = manifest["root"]
    return {
        "ok": recomputed == sealed_root,
        "root": sealed_root,
        "recomputed": recomputed,
    }
