"""Seal and verify: freezing identity, and confirming it (spec/claim-format.md,
spec/identity.md, spec/verification.md).

`seal` computes a claim's root from its pinned bytes and writes the store's
manifest (`.reticuli/manifest.json`: `{name, root}`). `verify` recomputes the
root from the bytes present now and reports whether it still matches the
sealed value -- identity only, no gate is executed. Editing a generated
output never moves the root; editing a pinned input, or any pinned/validated
step output, always does (spec/identity.md).
"""
import json
import os

from reticuli._kernel import core, identity, recipe

PARTS_RESIDUE = ".reticuli/parts.json"


def seal(d: str, **kwargs) -> dict:
    """Compute the root and write `.reticuli/manifest.json`.

    Returns the manifest written: `{"name": ..., "root": ...}`.
    """
    parsed = recipe.load_recipe(d)
    name = parsed["claim"]["name"]
    r = identity.root(parsed, d)
    os.makedirs(os.path.join(d, core.STORE), exist_ok=True)
    manifest = {"name": name, "root": r}
    core._write_json(os.path.join(d, core.MANIFEST), manifest)
    core._write_json(os.path.join(d, PARTS_RESIDUE), identity._parts(parsed, d))
    return manifest


def read_manifest(d: str) -> dict:
    """Read `.reticuli/manifest.json`; malformed bytes are refused, never crashed on."""
    path = os.path.join(d, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        raise core.ClaimError(f"no manifest at {path!r}: {e}") from e
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as e:
        raise core.ClaimError(f"malformed manifest {path!r}: {e}") from e
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)):
        raise core.ClaimError(f"malformed manifest {path!r}: missing name/root")
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present now and compare it with the
    sealed manifest -- identity only, no gate is executed (spec/verification.md).

    Returns `{"ok", "root", "recomputed"}`: `root` is the sealed value,
    `recomputed` is freshly computed from what is on disk now, and `ok` is
    their equality.
    """
    manifest = read_manifest(d)
    parsed = recipe.load_recipe(d)
    recomputed = identity.root(parsed, d)
    return {"ok": recomputed == manifest["root"], "root": manifest["root"],
            "recomputed": recomputed}


def _changed_parts(d: str) -> dict:
    """Which named parts of the root preimage differ from the sealed
    snapshot (store residue, outside identity) -- a diagnostic breakdown of
    why `verify` did or did not come back `ok`.

    `{}` when nothing is sealed yet, or every part still matches the
    snapshot taken at the last `seal`; otherwise maps a part name to its
    `[sealed, current]` hash pair for every part added, removed, or changed.
    """
    parsed = recipe.load_recipe(d)
    current = identity._parts(parsed, d)
    snapshot_path = os.path.join(d, PARTS_RESIDUE)
    if not os.path.isfile(snapshot_path):
        return {}
    with open(snapshot_path, "r", encoding="utf-8") as f:
        sealed = json.load(f)
    changed = {}
    for key in sealed.keys() | current.keys():
        before, after = sealed.get(key), current.get(key)
        if before != after:
            changed[key] = [before, after]
    return changed
