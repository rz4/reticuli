"""Seal a claim's identity and compare it with the bytes currently present."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Name preimage entries whose values differ between two computations."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Read a sealed manifest, refusing missing or malformed identity fields."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise core.ClaimError("manifest must be a JSON object")
    if not isinstance(manifest.get("name"), str) or not manifest["name"]:
        raise core.ClaimError("manifest needs a nonempty name")
    if not isinstance(manifest.get("root"), str) or not _ROOT.fullmatch(manifest["root"]):
        raise core.ClaimError("manifest needs a lowercase SHA-256 root")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict[str, str]:
    """Compute the claim root and write its identity manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Compare present pinned bytes with the sealed root, without running gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": (manifest["name"] == parsed["claim"]["name"]
                   and manifest["root"] == recomputed),
            "name": manifest["name"], "root": manifest["root"],
            "recomputed": recomputed}
