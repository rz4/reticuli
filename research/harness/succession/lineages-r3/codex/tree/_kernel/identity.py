"""Canonical identity and generated-byte digests for a claim."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Serialize with the JSON defaults fixed by the claim format."""
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _claim_format(recipe: dict) -> int:
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Remove producer guidance from format 3 without changing the input."""
    if _claim_format(recipe) < 3:
        return recipe
    result = recipe.copy()
    if "step" in recipe:
        result["step"] = [
            {key: value for key, value in step.items()
             if key not in core.GUIDANCE_KEYS}
            for step in recipe["step"]
        ]
    return result


def _parts(recipe: dict, directory: os.PathLike[str] | str) -> dict[str, str]:
    """Return the complete root preimage map."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8"),
    }
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        default_class = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default_class) not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: os.PathLike[str] | str) -> str:
    """Hash the recipe and every declared pinned file."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash present generated outputs as sorted path and file-hash pairs."""
    parsed = recipe_module.load_recipe(directory)
    present = []
    for name in sorted(recipe_module.generated_outputs(parsed)):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            present.append([name, core._hash_file(path)])
    return hashlib.sha256(_canonical(present)).hexdigest()
