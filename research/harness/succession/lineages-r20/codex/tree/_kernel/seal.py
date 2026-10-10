"""Seal a claim's content address and check it against present bytes."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Name the identity components whose values differ between two maps."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read a sealed claim's manifest, refusing malformed identity data."""
    path = core._safe(directory, core.MANIFEST)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"invalid manifest identity in {path}")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Freeze the recipe and pinned files into a manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare the sealed root with the root of the bytes now present."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": manifest["root"] == recomputed
            and manifest["name"] == parsed["claim"]["name"],
            "root": manifest["root"], "recomputed": recomputed}
