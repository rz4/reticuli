"""Seal a claim's identity and compare its present bytes with that seal."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Name preimage entries that were added, removed, or changed."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read a sealed manifest, refusing malformed or missing identity data."""
    path = os.path.join(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"invalid manifest identity: {path}")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Freeze the current recipe and pinned bytes into the claim manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare the present identity with the seal without executing gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": manifest["root"] == recomputed
            and manifest["name"] == parsed["claim"]["name"],
            "root": manifest["root"],
            "recomputed": recomputed}
