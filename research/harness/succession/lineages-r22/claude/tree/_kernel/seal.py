"""Sealing and verifying a claim's identity.

`seal` freezes a workspace into a claim: it computes the root from the
bytes present (`identity.root`) and writes `.reticuli/manifest.json`, pure
identity (`{name, root}`), carrying no hash of any generated output so that
editing the implementation never churns it (spec/claim-format.md).

`verify` answers "is this still the same claim?" by recomputing the root
from the bytes present and comparing it with the sealed manifest -- a hash
comparison, in milliseconds, never a gate re-run (spec/verification.md: the
`verify`/`audit` division). `read_manifest` reads the manifest back, refusing
malformed bytes rather than crashing on them.

`_changed_parts` is the diagnostic underneath a mismatch: given the parts
map a root was sealed from and the parts map it recomputes to, the sorted
keys whose value differs -- the `input:`/`pinned:` entries that moved, never
a `generated` byte, since those never entered either map.
"""
import json
import os

from . import core
from . import identity
from . import recipe as recipe_module
from .core import ClaimError


def _changed_parts(old: dict, new: dict) -> list:
    """Sorted keys whose value differs between two root parts maps."""
    keys = set(old) | set(new)
    return sorted(k for k in keys if old.get(k) != new.get(k))


def seal(d: str) -> dict:
    """Freeze `d` into a claim: compute its root, write the manifest."""
    recipe = recipe_module.load_recipe(d)
    name = recipe["claim"]["name"]
    r = identity.root(recipe, d)
    manifest = {"name": name, "root": r}

    path = os.path.join(d, core.MANIFEST)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    core._write_json(path, manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Read `.reticuli/manifest.json` back, refusing malformed bytes."""
    path = os.path.join(d, core.MANIFEST)
    if not os.path.isfile(path):
        raise ClaimError(f"no manifest at {path!r}: has this claim been sealed?")
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError) as exc:
        raise ClaimError(f"malformed manifest {path!r}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ClaimError(f"malformed manifest {path!r}: not a JSON object")
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        raise ClaimError(f"malformed manifest {path!r}: name must be a non-empty string")
    r = manifest.get("root")
    if (not isinstance(r, str) or len(r) != 64
            or any(c not in "0123456789abcdef" for c in r)):
        raise ClaimError(f"malformed manifest {path!r}: root must be 64 lowercase hex characters")
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present and compare it with the
    sealed manifest -- identity only, no gate is executed."""
    recipe = recipe_module.load_recipe(d)
    manifest = read_manifest(d)
    recomputed = identity.root(recipe, d)
    return {
        "ok": recomputed == manifest["root"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
