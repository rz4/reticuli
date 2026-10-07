"""Canonical identity and concrete build digests for a claim."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_module


def _canonical(value: object) -> bytes:
    """Serialize exactly as the claim identity format specifies."""
    try:
        return json.dumps(value, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"no canonical JSON form: {exc}") from exc


def _claim_format(claim_recipe: dict) -> int:
    return claim_recipe.get("claim", {}).get("format", 1)


def _preimage_recipe(claim_recipe: dict) -> dict:
    """Remove producer hints, and at format 4 order steps canonically."""
    version = _claim_format(claim_recipe)
    if version < 3:
        return claim_recipe
    preimage = dict(claim_recipe)
    steps = []
    for step in recipe_module._steps(claim_recipe):
        stripped = {key: value for key, value in step.items()
                    if key not in core.GUIDANCE_KEYS}
        steps.append(stripped)
    if version >= 4:
        steps.sort(key=lambda step: _canonical(step))
    if "step" in preimage:
        preimage["step"] = steps
    return preimage


def _parts(claim_recipe: dict, directory: str | os.PathLike[str]) -> dict[str, str]:
    """Build the map whose canonical JSON bytes name the claim."""
    parts = {
        "digest": core.DIGEST,
        "recipe": _canonical(_preimage_recipe(claim_recipe)).decode("utf-8"),
    }
    names = recipe_module._inputs(claim_recipe, directory)
    environment = claim_recipe.get("claim", {}).get("environment")
    if environment is not None:
        names.append(environment)
    for name in names:
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_module._steps(claim_recipe):
        step_class = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
        if step_class not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(claim_recipe: dict, directory: str | os.PathLike[str]) -> str:
    """SHA-256 name of a claim's canonical recipe and pinned bytes."""
    return hashlib.sha256(_canonical(_parts(claim_recipe, directory))).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """SHA-256 of the present, locally generated output names and hashes."""
    claim_recipe = recipe_module.load_recipe(directory)
    outputs = []
    for step in recipe_module.produces(claim_recipe):
        if step.get("class", "generated") not in ("generated", "free") or "from" in step:
            continue
        name = step["output"]
        path = core._safe(directory, name)
        if os.path.lexists(path):
            outputs.append([name, core._hash_file(path)])
    outputs.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(outputs)).hexdigest()
