"""Sealing and verification: freezing identity, and confirming it.

`seal` computes a claim's root (`identity.root`) from the bytes present and
writes it, with the claim's name, to `.reticuli/manifest.json` -- pure
identity, no hash of any generated output. `verify` recomputes the root from
the bytes present now and compares it with the sealed manifest: identity
only, no gate is executed (`spec/verification.md`). `read_manifest` reads
that file back, refusing malformed bytes rather than crashing. `_changed_parts`
is the diagnostic underneath both: given two preimage `parts` maps
(`identity._parts`), the sorted list of part-names whose hash differs --
which pinned input or output moved the root.
"""
import json
import os

from .core import ClaimError, MANIFEST, STORE, _write_json
from .identity import root
from .recipe import load_recipe


def _changed_parts(old: dict, new: dict) -> list:
    """Sorted preimage part-names whose value differs between two parts maps."""
    names = set(old) | set(new)
    return sorted(n for n in names if old.get(n) != new.get(n))


def seal(d: str) -> dict:
    """Freeze `d`: compute its root, write `.reticuli/manifest.json`."""
    recipe = load_recipe(d)
    manifest = {"name": recipe["claim"]["name"], "root": root(recipe, d)}
    os.makedirs(os.path.join(d, STORE), exist_ok=True)
    _write_json(os.path.join(d, MANIFEST), manifest)
    return manifest


def read_manifest(d: str) -> dict:
    """Read `d`'s manifest back: `{name, root}` (plus optional residue)."""
    path = os.path.join(d, MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except OSError as e:
        raise ClaimError(f"cannot read manifest {path!r}: {e}") from e
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed manifest {path!r}: {e}") from e
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)):
        raise ClaimError(f"malformed manifest {path!r}: missing name/root")
    return manifest


def verify(d: str) -> dict:
    """Recompute the root from the bytes present; compare with the seal.

    No gate is executed. Returns `{ok, root, recomputed}`: `root` is the
    sealed value, `recomputed` is fresh, `ok` is whether they match.
    """
    manifest = read_manifest(d)
    recipe = load_recipe(d)
    recomputed = root(recipe, d)
    return {
        "ok": recomputed == manifest["root"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
