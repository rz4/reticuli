"""Freeze and check a claim's content-addressed identity."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _manifest_path(directory: str | os.PathLike[str]) -> str:
    return os.path.join(directory, core.MANIFEST)


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """List preimage keys whose values differ between two calculations."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read a sealed manifest, refusing absent or malformed identity fields."""
    path = _manifest_path(directory)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or not _ROOT.fullmatch(manifest["root"])):
        raise core.ClaimError(f"invalid manifest {path}: expected name and SHA-256 root")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Compute the claim root and write its identity manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(_manifest_path(directory), manifest)
    return manifest


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare present pinned bytes with the root recorded at sealing."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"]
            and parsed["claim"]["name"] == manifest["name"],
            "root": manifest["root"],
            "recomputed": recomputed}
