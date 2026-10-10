"""Canonical claim identity and digest of present generated outputs."""

from __future__ import annotations

import copy
import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> str:
    """Use the JSON spelling specified for claim preimages."""
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise core.ClaimError(f"recipe has no canonical JSON form: {exc}") from exc


def _claim_format(recipe: dict) -> int:
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Return the recipe content that the declared format puts in identity."""
    result = copy.deepcopy(recipe)
    version = _claim_format(recipe)
    if version >= 3:
        for step in result.get("step", []):
            step.pop("guidance", None)
            step.pop("request", None)
    if version >= 4 and "step" in result:
        result["step"].sort(key=_canonical)
    return result


def _parts(recipe: dict, directory: str | os.PathLike[str]) -> dict[str, str]:
    """Construct the string map hashed to make a claim's root."""
    parts = {"digest": core.DIGEST, "recipe": _canonical(_preimage_recipe(recipe))}
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: str | os.PathLike[str]) -> str:
    return hashlib.sha256(_canonical(_parts(recipe, directory)).encode("utf-8")).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash the sorted (path, file digest) list of present local generated files."""
    recipe = recipe_module.load_recipe(directory)
    generated = []
    for step in recipe_module._steps(recipe):
        klass = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if klass != "generated" or "from" in step:
            continue
        name = step["output"]
        path = core._safe(directory, name)
        if os.path.exists(path):
            generated.append([name, core._hash_file(path)])
    generated.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(generated).encode("utf-8")).hexdigest()
