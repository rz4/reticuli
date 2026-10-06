"""Canonical claim identity and generated-byte digest."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import core, recipe as recipe_module


def _claim_format(recipe: dict[str, Any]) -> int:
    """Return the recipe format (the omitted version is format 1)."""
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return the recipe content covered by the root."""
    if _claim_format(recipe) < 3:
        return recipe
    cleaned = dict(recipe)
    cleaned["step"] = []
    for step in recipe.get("step", []):
        item = dict(step)
        if step.get("kind") == "produce":
            for key in core.GUIDANCE_KEYS:
                item.pop(key, None)
        cleaned["step"].append(item)
    return cleaned


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe has no canonical JSON form: {exc}") from exc


def _parts(recipe: dict[str, Any], directory: os.PathLike[str] | str) -> dict[str, str]:
    """Build the canonical root-preimage map."""
    parts = {"digest": core.DIGEST,
             "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8")}
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        if step.get("class", "generated" if step["kind"] == "produce" else "pinned") \
                not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict[str, Any], directory: os.PathLike[str] | str) -> str:
    """SHA-256 of the canonical, double-serialized claim preimage."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """SHA-256 of sorted present generated output names and file digests."""
    parsed = recipe_module.load_recipe(directory)
    outputs: list[list[str]] = []
    for name in recipe_module.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.exists(path):
            outputs.append([name, core._hash_file(path)])
    outputs.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(outputs)).hexdigest()
