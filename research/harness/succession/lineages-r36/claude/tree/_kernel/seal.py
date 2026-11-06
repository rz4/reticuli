"""Freezing identity, and confirming it.

`seal` records the root onto the manifest; `verify` recomputes it from the
bytes present and reports whether they still hash to the sealed value. That
is the whole of it: verify executes NO gate. Identity is a hash comparison
and answers "is this still the same claim?" in milliseconds; a verdict is
earned only by running the gates, which is `audit`'s job. A verifier that
ran gates under the name `verify` would blur the one distinction the whole
design exists to keep sharp.
"""
import os

from . import identity as _identity
from . import recipe as _recipe
from .core import (MANIFEST, PARTS, ClaimError, _read_json, _write_json)


def read_manifest(claim: str) -> dict:
    """`{name, root}`, plus whatever residue a layer above attached.

    Malformed bytes are refused: a damaged claim is not data.
    """
    path = os.path.join(claim, MANIFEST)
    if not os.path.isfile(path):
        raise ClaimError(f"no sealed manifest in {claim}")
    manifest = _read_json(path)
    if not isinstance(manifest, dict):
        raise ClaimError(f"{path} is not a manifest")
    if not isinstance(manifest.get("name"), str):
        raise ClaimError(f"{path}: a manifest's name must be a string")
    if not isinstance(manifest.get("root"), str):
        raise ClaimError(f"{path}: a manifest's root must be a string")
    return manifest


def _hold_constrains(parsed: dict, claim: str) -> None:
    """A declared criterion target must be an output this claim OWNS.

    A criterion declared over a supplied module constrains a file that never
    ships -- the gate validates the producer's local copy, and assembly
    discards it for the owning room's -- so the seal refuses and names the
    claim the criterion belongs in.
    """
    table = parsed.get("claim") or {}
    constrains = table.get("constrains")
    if not isinstance(constrains, dict):
        return
    owned, supplied = {}, {}
    for step in _recipe.produces(parsed):
        if step.get("from"):
            supplied[step["output"]] = step["from"]
        else:
            owned[step["output"]] = True
    for criterion, targets in constrains.items():
        for target in targets:
            if target in owned:
                continue
            if target in supplied:
                raise ClaimError(
                    f"{criterion!r} is declared to constrain {target!r}, "
                    f"which this claim is SUPPLIED from the component "
                    f"{supplied[target]!r}: the gate would validate a copy "
                    f"that never ships. The criterion belongs in "
                    f"{supplied[target]!r}")
            raise ClaimError(
                f"{criterion!r} is declared to constrain {target!r}, which "
                f"this claim declares no produce step for")


def seal(claim: str, **residue) -> dict:
    """Compute the root and write the manifest; hand back what was written.

    A caller one layer down reads `seal(d)["root"]`, so the manifest comes
    back rather than None -- the schema beyond name/root stays free, those
    two coming back as strings does not.
    """
    parsed = _recipe.load_recipe(claim)
    _hold_constrains(parsed, claim)
    parts = _identity._parts(parsed, claim)
    import hashlib
    import json
    computed = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()

    path = os.path.join(claim, MANIFEST)
    manifest = {}
    if os.path.isfile(path):
        existing = _read_json(path)
        if isinstance(existing, dict):
            manifest = dict(existing)
    manifest["name"] = parsed["claim"]["name"]
    manifest["root"] = computed
    for key, value in residue.items():
        if value is None:
            continue
        manifest[key] = value
    _write_json(path, manifest)
    # the preimage, as residue: so a broken verify can NAME what moved
    _write_json(os.path.join(claim, PARTS), parts)
    return manifest


def _changed_parts(claim: str, parsed: dict | None = None) -> list:
    """Which declared paths no longer hash to what the seal recorded.

    Residue, so it is advisory: where the sealed preimage was never written
    or has been discarded, nothing is named rather than something guessed.
    """
    sealed = _read_json(os.path.join(claim, PARTS))
    if not isinstance(sealed, dict):
        return []
    if parsed is None:
        try:
            parsed = _recipe.load_recipe(claim)
        except ClaimError:
            return []
    try:
        present = _identity._parts(parsed, claim)
    except ClaimError:
        return []
    moved = []
    for key in sorted(set(sealed) | set(present)):
        if key in ("digest", "recipe"):
            if sealed.get(key) != present.get(key) and key == "recipe":
                moved.append(_recipe.recipe_path(claim).rsplit(os.sep, 1)[-1])
            continue
        if sealed.get(key) != present.get(key):
            moved.append(key.split(":", 1)[-1])
    return moved


def verify(claim: str) -> dict:
    """Recompute the root from the bytes present and compare. No gate runs."""
    parsed = _recipe.load_recipe(claim)
    manifest = read_manifest(claim)
    recomputed = _identity.root(parsed, claim)
    sealed = manifest["root"]
    result = {"name": manifest["name"],
              "root": sealed,
              "recomputed": recomputed,
              "ok": recomputed == sealed}
    if not result["ok"]:
        result["changed"] = _changed_parts(claim, parsed)
    return result
