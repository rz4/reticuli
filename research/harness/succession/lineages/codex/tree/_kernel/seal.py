"""Record and verify the content identity of a claim."""

from __future__ import annotations

import json
import os
from typing import Any

from . import core, identity, recipe


def _changed_parts(stored: list[list[str]], current: list[list[str]]) -> list[str]:
    """Return input paths whose recorded and current digests differ."""
    before = dict(stored)
    after = dict(current)
    return sorted(name for name in before.keys() | after.keys()
                  if before.get(name) != after.get(name))


def read_manifest(directory: str) -> dict[str, Any]:
    """Read the seal written in the claim's manifest."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise core.ClaimError("manifest must be a JSON object")
    return manifest


def seal(directory: str) -> dict[str, Any]:
    """Store the root derived from the recipe and its declared input bytes."""
    data = recipe.load_recipe(directory)
    manifest = {
        "format": identity._claim_format(data),
        "name": data["claim"]["name"],
        "root": identity.root(data, directory),
        "inputs": identity._parts(data, directory),
    }
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str) -> dict[str, Any]:
    """Compare the present claim identity with its recorded seal."""
    manifest = read_manifest(directory)
    data = recipe.load_recipe(directory)
    recomputed = identity.root(data, directory)
    current_parts = identity._parts(data, directory)
    stored_parts = manifest.get("inputs", [])
    changed = _changed_parts(stored_parts, current_parts)
    return {
        "ok": manifest.get("root") == recomputed,
        "root": manifest.get("root"),
        "recomputed": recomputed,
        "changed_parts": changed,
    }
