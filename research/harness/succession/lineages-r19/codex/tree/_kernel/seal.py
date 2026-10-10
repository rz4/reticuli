"""Seal a claim's identity and compare it with the bytes currently present."""

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


def read_manifest(directory: os.PathLike[str] | str) -> dict:
    """Read the sealed identity, refusing missing or malformed manifests."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"invalid manifest: {path}")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict:
    """Hash a claim's declared pins and write its manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict:
    """Compare the current identity to the sealed root without running gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"]
            and parsed["claim"]["name"] == manifest["name"],
            "name": manifest["name"], "root": manifest["root"],
            "recomputed": recomputed}
