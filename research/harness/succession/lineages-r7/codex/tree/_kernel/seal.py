"""Seal a claim's identity and compare it with the bytes present later."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read the sealed identity, refusing an absent or malformed manifest."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise core.ClaimError(f"cannot read manifest {path}: {error}") from error
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"malformed manifest: {path}")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Compute the identity and write it to the claim's manifest."""
    claim_recipe = recipe.load_recipe(directory)
    manifest = {
        "name": claim_recipe["claim"]["name"],
        "root": identity.root(claim_recipe, directory),
    }
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def _changed_parts(before: Mapping, after: Mapping) -> list[str]:
    """Name canonical preimage entries whose values differ."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def verify(directory: str | os.PathLike[str]) -> dict:
    """Check identity against the manifest without executing gates."""
    manifest = read_manifest(directory)
    claim_recipe = recipe.load_recipe(directory)
    recomputed = identity.root(claim_recipe, directory)
    return {
        "ok": (manifest["name"] == claim_recipe["claim"]["name"]
               and manifest["root"] == recomputed),
        "name": manifest["name"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
