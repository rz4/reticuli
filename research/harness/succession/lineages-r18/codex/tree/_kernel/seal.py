"""Freeze a claim's identity and compare its present bytes with that seal."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

from . import core, identity, recipe


_ROOT = re.compile(r"[0-9a-f]{64}\Z")


def _changed_parts(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Name the preimage entries whose values differ between two readings."""
    return sorted(key for key in before.keys() | after.keys()
                  if before.get(key) != after.get(key))


def read_manifest(claim_dir: os.PathLike[str] | str) -> dict[str, object]:
    """Read a sealed manifest, refusing malformed identity data."""
    path = os.path.join(os.fspath(claim_dir), core.MANIFEST)
    try:
        with open(path, "r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise core.ClaimError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise core.ClaimError("manifest must be a JSON object")
    if not isinstance(manifest.get("name"), str):
        raise core.ClaimError("manifest name must be a string")
    value = manifest.get("root")
    if not isinstance(value, str) or _ROOT.fullmatch(value) is None:
        raise core.ClaimError("manifest root must be a lowercase SHA-256 digest")
    return manifest


def seal(claim_dir: os.PathLike[str] | str) -> dict[str, str]:
    """Compute the root from the current criteria and record it atomically."""
    document = recipe.load_recipe(claim_dir)
    manifest = {"name": document["claim"]["name"],
                "root": identity.root(document, claim_dir)}
    core._write_json(os.path.join(os.fspath(claim_dir), core.MANIFEST), manifest)
    return manifest


def verify(claim_dir: os.PathLike[str] | str) -> dict[str, object]:
    """Compare present criteria with the recorded root without running gates."""
    manifest = read_manifest(claim_dir)
    document = recipe.load_recipe(claim_dir)
    recomputed = identity.root(document, claim_dir)
    return {"ok": manifest["root"] == recomputed,
            "root": manifest["root"], "recomputed": recomputed}
