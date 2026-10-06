"""Freeze and check the identity of a local claim."""

from __future__ import annotations

import json
import os
import re

from . import core, identity, recipe as recipe_module


_ROOT_RE = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: dict, after: dict) -> list[str]:
    """Name the entries whose values differ between two identity preimages."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str) -> dict:
    """Read a sealed manifest, refusing missing or malformed identity data."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT_RE.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"malformed manifest {path}: expected name and root")
    return manifest


def seal(directory: str) -> dict:
    """Compute the root from declared bytes and write the identity manifest."""
    recipe = recipe_module.load_recipe(directory)
    manifest = {"name": recipe["claim"]["name"],
                "root": identity.root(recipe, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str) -> dict:
    """Compare present pinned bytes with the sealed identity, without gates."""
    manifest = read_manifest(directory)
    recipe = recipe_module.load_recipe(directory)
    recomputed = identity.root(recipe, directory)
    return {"ok": manifest["root"] == recomputed
            and manifest["name"] == recipe["claim"]["name"],
            "name": manifest["name"],
            "root": manifest["root"],
            "recomputed": recomputed}
