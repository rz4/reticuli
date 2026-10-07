"""Store a claim's content address and check it against present bytes."""

from __future__ import annotations

import json
import os
import re

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: dict, after: dict) -> list[str]:
    """Name identity components that differ between two preimages."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: str | os.PathLike[str]) -> dict:
    """Read the sealed manifest, refusing missing or malformed contents."""
    path = os.path.join(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or not _ROOT.fullmatch(manifest["root"])):
        raise core.ClaimError(f"invalid manifest {path}: expected name and SHA-256 root")
    return manifest


def seal(directory: str | os.PathLike[str]) -> dict:
    """Compute a claim root and write its identity manifest."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(os.path.join(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: str | os.PathLike[str]) -> dict:
    """Compare the current pinned bytes with the sealed root, without gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": recomputed == manifest["root"],
            "root": manifest["root"], "recomputed": recomputed}
