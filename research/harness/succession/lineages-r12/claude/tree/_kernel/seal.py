"""Seal and verify: freezing a claim's identity, and confirming it.

`seal` computes a claim's root from the bytes present now and records it
onto `.reticuli/manifest.json` (`{name, root}`, `spec/claim-format.md`).
`verify` recomputes the root from the bytes present and compares it against
the sealed value -- identity only; **no gate runs here** (`spec/verification.md`:
the verify/audit split is load-bearing).

Alongside the manifest, `seal` also writes a snapshot of the named parts
that went into the root (`spec/identity.md`'s `parts` map) as store residue,
outside identity, so that `_changed_parts` can name which pinned part moved
when identity breaks instead of only reporting that it did.

Stdlib only.
"""
import json
import os

from . import core
from . import identity
from . import recipe as recipe_mod

PARTS_RESIDUE = os.path.join(core.STORE, "parts.json")


def _hash_parts(parts: dict) -> str:
    """The root: sha256 of the canonical serialization of `parts`."""
    import hashlib
    return hashlib.sha256(identity._canonical_json(parts).encode("utf-8")).hexdigest()


def _current_parts(d: str) -> dict:
    recipe = recipe_mod.load_recipe(d)
    return identity._parts(recipe, d)


def seal(d: str) -> dict:
    """Compute the root from the bytes present and write the manifest.

    Writes `.reticuli/manifest.json` (`{name, root}`) and a parts snapshot
    (store residue, used only by `_changed_parts`). Returns the manifest.
    """
    recipe = recipe_mod.load_recipe(d)
    parts = identity._parts(recipe, d)
    root = _hash_parts(parts)
    name = recipe["claim"]["name"]
    manifest = {"name": name, "root": root}

    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    core._write_json(os.path.join(d, PARTS_RESIDUE), parts)
    return manifest


def read_manifest(d: str) -> dict:
    """Read `.reticuli/manifest.json`: `{name, root}`. Malformed bytes refused."""
    path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(path):
        raise core.ClaimError(f"refused: no manifest at {path!r} -- claim not sealed")
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise core.ClaimError(f"refused: malformed manifest {path!r}: {e}") from e
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)):
        raise core.ClaimError(f"refused: malformed manifest {path!r}: missing name/root")
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it to the sealed one.

    Identity only -- no gate is executed (`spec/verification.md`). Returns
    `{"ok": bool, "root": <sealed root>, "recomputed": <root from bytes now>}`.
    """
    manifest = read_manifest(d)
    recomputed = _hash_parts(_current_parts(d))
    return {
        "ok": recomputed == manifest["root"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }


def _changed_parts(d: str) -> dict:
    """Which named parts (`spec/identity.md`) moved since the claim was sealed.

    Diagnostic only, built from the parts snapshot `seal` wrote as residue:
    for each key present before and/or now whose hash differs, reports
    `{"was": <old hash or None>, "now": <new hash or None>}`.
    """
    path = os.path.join(d, PARTS_RESIDUE)
    if not os.path.isfile(path):
        raise core.ClaimError(f"refused: no parts snapshot at {path!r} -- claim not sealed")
    try:
        with open(path, "r", encoding="utf-8") as f:
            before = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise core.ClaimError(f"refused: malformed parts snapshot {path!r}: {e}") from e

    after = _current_parts(d)
    changed = {}
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changed[key] = {"was": old, "now": new}
    return changed
