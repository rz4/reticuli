"""Seal a claim's identity and verify it against the present pinned bytes."""

from __future__ import annotations

import json
import os
import re

from . import core, identity, recipe as recipe_module


_ROOT_RE = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: dict, after: dict) -> list[str]:
    """Name identity components whose values differ between two snapshots."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read a sealed manifest, refusing missing or malformed identity data."""
    path = core._safe(directory, core.MANIFEST)
    try:
        core._hash_file(path)
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not manifest["name"]
            or not isinstance(manifest.get("root"), str)
            or _ROOT_RE.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"malformed manifest {path}")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Compute the current claim root and persist its name and root."""
    claim_recipe = recipe_module.load_recipe(directory)
    manifest = {
        "name": claim_recipe["claim"]["name"],
        "root": identity.root(claim_recipe, directory),
    }
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare current pinned bytes to the sealed root, without running gates."""
    manifest = read_manifest(directory)
    claim_recipe = recipe_module.load_recipe(directory)
    recomputed = identity.root(claim_recipe, directory)
    return {
        "ok": manifest["root"] == recomputed
              and manifest["name"] == claim_recipe["claim"]["name"],
        "name": manifest["name"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
