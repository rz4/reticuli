"""Canonical identity and build digests for claims."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping

from . import core, recipe as recipe_module


def _canonical(value: object) -> str:
    """Serialize with the identity format's default JSON whitespace."""
    return json.dumps(value, sort_keys=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _claim_format(recipe: Mapping[str, object]) -> int:
    return recipe["claim"].get("format", 1)


def _preimage_recipe(recipe: Mapping[str, object]) -> dict:
    """Return the acceptance-bearing portion of a parsed recipe."""
    result = dict(recipe)
    version = _claim_format(recipe)
    if version >= 3 and "step" in recipe:
        steps = []
        for step in recipe["step"]:
            cleaned = {key: value for key, value in step.items()
                       if key not in core.GUIDANCE_KEYS}
            steps.append(cleaned)
        if version >= 4:
            steps.sort(key=_canonical)
        result["step"] = steps
    return result


def _parts(recipe: Mapping[str, object], directory: os.PathLike[str] | str) -> dict[str, str]:
    """Build the string map whose canonical JSON digest names the claim."""
    parts = {"digest": core.DIGEST,
             "recipe": _canonical(_preimage_recipe(recipe))}
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        classification = step.get("class", "generated" if step["kind"] == "produce"
                                  else "pinned")
        if classification != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: Mapping[str, object], directory: os.PathLike[str] | str) -> str:
    """Compute a claim's content address from its parsed recipe and pinned bytes."""
    return _digest(_parts(recipe, directory))


def build_digest(directory: os.PathLike[str] | str) -> str:
    """Digest the generated outputs present in a claim directory."""
    parsed = recipe_module.load_recipe(directory)
    generated = []
    for name in recipe_module.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.exists(path):
            generated.append([name, core._hash_file(path)])
    generated.sort(key=lambda pair: pair[0])
    return _digest(generated)
