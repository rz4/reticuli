"""Freeze and verify a claim's content-addressed identity."""

from __future__ import annotations

import json
import os
import re

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: dict, after: dict) -> list[str]:
    """Name preimage parts whose values differ between two readings."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: os.PathLike[str] | str) -> dict:
    """Read the sealed name and root, refusing missing or malformed residue."""
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
        raise core.ClaimError(f"malformed manifest {path}")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict:
    """Compute the identity from declared pinned bytes and record it."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict:
    """Compare present pinned bytes with the sealed identity."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"],
            "name": manifest["name"], "root": manifest["root"],
            "recomputed": recomputed}
