"""Canonical identity and generated-byte digests for a claim."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Serialize with the exact JSON defaults used by claim identities."""
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe has no canonical JSON form: {exc}") from exc


def _claim_format(recipe: dict) -> int:
    """Return the declared format, with the original format as default."""
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Remove authoring hints and order steps as required by the format."""
    version = _claim_format(recipe)
    if version < 3:
        return recipe

    preimage = dict(recipe)
    if "step" in recipe:
        steps = []
        for step in recipe["step"]:
            item = dict(step)
            if item.get("kind") == "produce":
                for key in core.GUIDANCE_KEYS:
                    item.pop(key, None)
            steps.append(item)
        if version >= 4:
            steps.sort(key=lambda step: _canonical(step))
        preimage["step"] = steps
    return preimage


def _parts(recipe: dict, directory: os.PathLike[str] | str) -> dict[str, str]:
    """Assemble the string map whose canonical JSON is the root preimage."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(recipe)).decode("utf-8"),
    }
    inputs = recipe_module._inputs(recipe, directory)
    environment = recipe["claim"].get("environment")
    if environment is not None:
        inputs.append(environment)
    for name in inputs:
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step_class != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: os.PathLike[str] | str) -> str:
    """Hash the parsed recipe and all files it pins."""
    return hashlib.sha256(_canonical(_parts(recipe, directory))).hexdigest()


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Hash present generated outputs owned by this claim."""
    parsed = recipe_module.load_recipe(directory)
    files = []
    for name in recipe_module.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            files.append((name, core._hash_file(path)))
    files.sort()
    return hashlib.sha256(_canonical(files)).hexdigest()
