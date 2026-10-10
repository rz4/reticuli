"""Seal a claim's identity and compare present bytes with its seal."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str],
                   after: Mapping[str, str]) -> list[str]:
    """List preimage entries whose values differ between two identities."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: os.PathLike[str] | str) -> dict:
    """Read a sealed manifest, refusing missing or malformed identity fields."""
    path = core._safe(directory, core.MANIFEST)
    try:
        core._hash_file(path)
        with open(path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or _ROOT.fullmatch(manifest["root"]) is None):
        raise core.ClaimError(f"invalid manifest in {path}: expected name and SHA-256 root")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict:
    """Compute the identity of pinned bytes and write it to the store."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict:
    """Compare current pinned bytes with the stored root; do not run gates."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": manifest["root"] == recomputed
            and manifest["name"] == parsed["claim"]["name"],
            "root": manifest["root"],
            "recomputed": recomputed}
