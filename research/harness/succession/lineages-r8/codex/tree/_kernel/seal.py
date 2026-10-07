"""Seal a claim's identity and compare its present bytes with that seal."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _manifest_path(directory: str | os.PathLike[str]) -> str:
    return core._safe(directory, core.MANIFEST)


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read a sealed manifest, refusing missing or malformed identity data."""
    path = _manifest_path(directory)
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(document, dict)
            or not isinstance(document.get("name"), str)
            or not isinstance(document.get("root"), str)
            or _ROOT.fullmatch(document["root"]) is None):
        raise core.ClaimError(f"malformed manifest: {path}")
    return document


def _changed_parts(before: dict, after: dict) -> list[str]:
    """Name identity components whose values differ between two preimages."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def seal(directory: str | os.PathLike[str]) -> dict:
    """Compute the root from pinned bytes and write the identity manifest."""
    claim_recipe = recipe.load_recipe(directory)
    document = {
        "name": claim_recipe["claim"]["name"],
        "root": identity.root(claim_recipe, directory),
    }
    core._write_json(_manifest_path(directory), document)
    return document


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare present pinned bytes with the sealed root, without running gates."""
    manifest = read_manifest(directory)
    claim_recipe = recipe.load_recipe(directory)
    recomputed = identity.root(claim_recipe, directory)
    return {
        "ok": manifest["root"] == recomputed
              and manifest["name"] == claim_recipe["claim"]["name"],
        "name": manifest["name"],
        "root": manifest["root"],
        "recomputed": recomputed,
    }
