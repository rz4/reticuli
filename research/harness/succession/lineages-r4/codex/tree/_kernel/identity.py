"""Canonical identity and concrete build digests for a claim."""

from __future__ import annotations

import copy
import hashlib
import json
import os

from . import core, recipe as recipe_module


def _claim_format(recipe: dict) -> int:
    """Return the declared format, including the format-1 default."""
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Return the recipe represented by the identity preimage."""
    if _claim_format(recipe) < 3:
        return recipe
    result = copy.deepcopy(recipe)
    for step in result.get("step", []):
        for key in core.GUIDANCE_KEYS:
            step.pop(key, None)
    return result


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be canonically serialized: {exc}") from exc


def _parts(recipe: dict, directory: os.PathLike[str] | str) -> dict[str, str]:
    """Gather the named, hashed pieces of a root preimage."""
    parts = {"digest": core.DIGEST,
             "recipe": _canonical(_preimage_recipe(recipe)).decode("ascii")}
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        default_class = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default_class) != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: os.PathLike[str] | str) -> str:
    """Hash the canonical recipe and every declared pinned file."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash a sorted list of present, locally generated output hashes."""
    parsed = recipe_module.load_recipe(directory)
    files = []
    for step in recipe_module.produces(parsed):
        if step.get("class", "generated") != "generated" or "from" in step:
            continue
        name = step["output"]
        path = core._safe(directory, name)
        if os.path.exists(path):
            files.append([name, core._hash_file(path)])
    return hashlib.sha256(_canonical(sorted(files))).hexdigest()
