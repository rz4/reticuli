"""Canonical identity and concrete build digests for local claims."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Serialize with the identity format's exact JSON defaults."""
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be serialized as canonical JSON: {exc}") from exc


def _claim_format(recipe: dict) -> int:
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Omit producer hints from format-3 identities without changing the source."""
    if _claim_format(recipe) < 3:
        return recipe
    result = dict(recipe)
    if "step" in result:
        result["step"] = [
            {key: value for key, value in step.items()
             if key not in core.GUIDANCE_KEYS or step.get("kind") != "produce"}
            for step in result["step"]
        ]
    return result


def _parts(recipe: dict, directory: str) -> dict[str, str]:
    """Collect the exact values that define a claim's root."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8"),
    }
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        default = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default) != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: str) -> str:
    """Return the content address of the recipe and its pinned bytes."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: str) -> str:
    """Hash present, locally generated outputs as sorted name/hash pairs."""
    recipe = recipe_module.load_recipe(directory)
    entries = []
    for name in recipe_module.generated_outputs(recipe):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            entries.append([name, core._hash_file(path)])
    entries.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(entries)).hexdigest()
