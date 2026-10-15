"""Canonical claim identity and generated-byte digest."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping

from . import core, recipe as recipe_module


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be serialized as canonical JSON: {exc}") from exc


def _claim_format(recipe: Mapping) -> int:
    """Return the declared identity format, defaulting to format one."""
    return recipe.get("claim", {}).get("format", 1)


def _preimage_recipe(recipe: Mapping) -> dict:
    """Copy the parsed recipe, removing fields outside the selected format's identity."""
    preimage = dict(recipe)
    version = _claim_format(recipe)
    if version >= 3 and "step" in preimage:
        steps = [dict(step) for step in preimage["step"]]
        for step in steps:
            for key in core.GUIDANCE_KEYS:
                step.pop(key, None)
        if version >= 4:
            steps.sort(key=_canonical)
        preimage["step"] = steps
    return preimage


def _parts(recipe: Mapping, directory: str | os.PathLike[str]) -> dict[str, str]:
    """Build the root's string-to-string preimage map."""
    parts = {"digest": core.DIGEST, "recipe": _canonical(_preimage_recipe(recipe))}
    for name in recipe_module._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(recipe):
        default_class = "generated" if step["kind"] == "produce" else "pinned"
        if step.get("class", default_class) != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: Mapping, directory: str | os.PathLike[str]) -> str:
    """Hash the canonical recipe and every declared pinned file."""
    return hashlib.sha256(_canonical(_parts(recipe, directory)).encode("utf-8")).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Hash a sorted list of present, locally generated output digests."""
    parsed = recipe_module.load_recipe(directory)
    generated = []
    for name in recipe_module.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            generated.append((name, core._hash_file(path)))
    generated.sort()
    return hashlib.sha256(_canonical(generated).encode("utf-8")).hexdigest()
