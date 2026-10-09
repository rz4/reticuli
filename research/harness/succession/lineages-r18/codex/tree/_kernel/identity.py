"""Canonical claim identity and generated-byte digest."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping

from . import core, recipe as recipe_module


def _canonical(value: object) -> str:
    """Serialize a preimage with the identity format's JSON defaults."""
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be serialized as canonical JSON: {exc}") from exc


def _claim_format(recipe: Mapping[str, object]) -> int:
    claim = recipe.get("claim")
    if not isinstance(claim, Mapping):
        raise core.ClaimError("recipe needs a [claim] table")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1 or version > core.FORMAT:
        raise core.ClaimError(f"invalid or unsupported claim format: {version!r}")
    return version


def _preimage_recipe(recipe: Mapping[str, object]) -> dict[str, object]:
    """Return the recipe represented by a root, without changing the source."""
    version = _claim_format(recipe)
    result = dict(recipe)
    if version >= 3 and "step" in result:
        steps = []
        for step in recipe_module._steps(recipe):
            stripped = dict(step)
            for key in core.GUIDANCE_KEYS:
                stripped.pop(key, None)
            steps.append(stripped)
        if version >= 4:
            steps.sort(key=_canonical)
        result["step"] = steps
    return result


def _parts(recipe: Mapping[str, object], claim_dir: os.PathLike[str] | str) -> dict[str, str]:
    """Collect every identity-bearing digest into the root preimage."""
    parts = {"digest": core.DIGEST, "recipe": _canonical(_preimage_recipe(recipe))}
    for name in recipe_module._inputs(recipe, claim_dir):
        parts["input:" + name] = core._hash_file(core._safe(claim_dir, name))
    for step in recipe_module._steps(recipe):
        kind = step["kind"]
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class != "generated":
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(claim_dir, name))
    return parts


def root(recipe: Mapping[str, object], claim_dir: os.PathLike[str] | str) -> str:
    """Compute the identity of a claim's criteria and pinned bytes."""
    return hashlib.sha256(_canonical(_parts(recipe, claim_dir)).encode("utf-8")).hexdigest()


def build_digest(claim_dir: os.PathLike[str] | str) -> str:
    """Digest generated outputs present in a claim, excluding supplied ones."""
    recipe = recipe_module.load_recipe(claim_dir)
    generated = []
    for step in recipe_module._steps(recipe):
        kind = step["kind"]
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class != "generated" or "from" in step:
            continue
        name = step["output"]
        path = core._safe(claim_dir, name)
        if os.path.exists(path):
            generated.append([name, core._hash_file(path)])
    generated.sort(key=lambda item: item[0])
    return hashlib.sha256(_canonical(generated).encode("utf-8")).hexdigest()
