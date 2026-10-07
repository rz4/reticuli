"""Canonical identity and concrete build digests for a claim."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Encode a preimage with the format's default JSON separators."""
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def _claim_format(recipe: dict) -> int:
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Return the recipe content that is identity bearing at its format."""
    version = _claim_format(recipe)
    if version < 3:
        return recipe

    result = dict(recipe)
    steps = []
    for step in recipe.get("step", []):
        copied = {key: value for key, value in step.items()
                  if key not in core.GUIDANCE_KEYS}
        steps.append(copied)
    if version >= 4:
        steps.sort(key=_canonical)
    if "step" in recipe:
        result["step"] = steps
    return result


def _parts(recipe: dict, directory: str | os.PathLike[str]) -> dict[str, str]:
    """Construct the exact string map hashed to form the claim root."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8"),
    }
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe.get("step", []):
        kind = step["kind"]
        classification = step.get("class", "generated" if kind == "produce" else "pinned")
        if classification not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: str | os.PathLike[str]) -> str:
    """Return the content address of a parsed claim and its pinned files."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash the present, locally generated outputs as sorted path/digest pairs."""
    claim = recipe_module.load_recipe(directory)
    pairs = []
    for name in recipe_module.generated_outputs(claim):
        path = core._safe(directory, name)
        if os.path.exists(path):
            pairs.append((name, core._hash_file(path)))
    pairs.sort()
    return hashlib.sha256(_canonical(pairs)).hexdigest()
