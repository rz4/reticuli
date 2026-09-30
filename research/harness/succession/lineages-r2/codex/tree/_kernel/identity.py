"""Content addresses for claims and their generated files."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Use the claim format's default-spaced, ASCII JSON serialization."""
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _claim_format(recipe: Mapping) -> int:
    return recipe.get("claim", {}).get("format", 1)


def _preimage_recipe(recipe: Mapping) -> dict:
    """Remove producer hints from format-3 identity without mutating the caller."""
    if _claim_format(recipe) < 3:
        return dict(recipe)
    result = dict(recipe)
    if "step" in result:
        result["step"] = [
            {key: value for key, value in step.items()
             if not (step.get("kind") == "produce" and key in core.GUIDANCE_KEYS)}
            for step in result["step"]
        ]
    return result


def _parts(recipe: Mapping, directory: os.PathLike[str] | str) -> dict[str, str]:
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)).decode("ascii"),
    }
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step_class not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: Mapping, directory: os.PathLike[str] | str) -> str:
    """Return the SHA-256 identity of the recipe and pinned bytes."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash the generated files present in a realization."""
    parsed = recipe_module.load_recipe(directory)
    files = []
    for step in recipe_module.produces(parsed):
        if step.get("class", "generated") not in ("generated", "free") or "from" in step:
            continue
        name = step["output"]
        path = core._safe(directory, name)
        if os.path.exists(path):
            files.append([name, core._hash_file(path)])
    files.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(files)).hexdigest()
