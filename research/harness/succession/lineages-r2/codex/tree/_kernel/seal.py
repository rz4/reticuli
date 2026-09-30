"""Freeze a claim's identity and compare present bytes with its seal."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Name preimage components whose values differ between two computations."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: os.PathLike[str] | str) -> dict:
    """Read the sealed name and root, refusing malformed manifest content."""
    path = core._safe(directory, core.MANIFEST)
    try:
        core._hash_file(path)
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"invalid manifest {path}: expected name and SHA-256 root")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict:
    """Compute identity from the recipe and pinned files, then store it."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict:
    """Compare the current identity with the saved one without running gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"],
            "root": manifest["root"],
            "recomputed": recomputed}
