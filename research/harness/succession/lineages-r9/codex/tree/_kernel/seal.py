"""Store a claim's identity and compare it with the bytes now present."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT_RE = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """List the identity parts whose values differ between two snapshots."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(directory: os.PathLike[str] | str) -> dict:
    """Read the stored claim identity, refusing malformed manifest bytes."""
    path = core._safe(directory, core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("name"), str)
            or not isinstance(manifest.get("root"), str)
            or not _ROOT_RE.fullmatch(manifest["root"])):
        raise core.ClaimError(f"malformed manifest {path}")
    return manifest


def seal(directory: os.PathLike[str] | str) -> dict[str, str]:
    """Compute the root and atomically write its name and root to the store."""
    parsed = recipe.load_recipe(directory)
    manifest = {"name": parsed["claim"]["name"],
                "root": identity.root(parsed, directory)}
    core._write_json(core._safe(directory, core.MANIFEST), manifest)
    return manifest


def verify(directory: os.PathLike[str] | str) -> dict:
    """Compare the current pinned bytes with the stored identity."""
    manifest = read_manifest(directory)
    parsed = recipe.load_recipe(directory)
    recomputed = identity.root(parsed, directory)
    return {"ok": manifest["root"] == recomputed,
            "name": manifest["name"],
            "root": manifest["root"],
            "recomputed": recomputed}
