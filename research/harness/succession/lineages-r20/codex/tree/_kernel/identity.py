"""Canonical claim identity and concrete build digests."""

from __future__ import annotations

import hashlib
import json
import os

from . import core, recipe as recipe_reader


def _canonical(value: object) -> str:
    """Serialize a preimage using the claim format's JSON convention."""
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be serialized as canonical JSON: {exc}") from exc


def _claim_format(recipe: dict) -> int:
    return recipe.get("claim", {}).get("format", 1)


def _preimage_recipe(recipe: dict) -> dict:
    """Return the recipe content that belongs to this format's root."""
    version = _claim_format(recipe)
    if version < 3:
        return recipe
    result = dict(recipe)
    steps = []
    for step in recipe_reader._steps(recipe):
        item = {key: value for key, value in step.items()
                if key not in core.GUIDANCE_KEYS}
        steps.append(item)
    if version >= 4:
        steps.sort(key=_canonical)
    if "step" in recipe:
        result["step"] = steps
    return result


def _parts(recipe: dict, directory: str | os.PathLike[str]) -> dict[str, str]:
    parts = {"digest": core.DIGEST, "recipe": _canonical(_preimage_recipe(recipe))}
    for name in recipe_reader._inputs(recipe, directory):
        parts["input:" + name] = core._hash_file(core._safe(directory, name))
    for step in recipe_reader._steps(recipe):
        kind = step.get("kind")
        cls = step.get("class", "generated" if kind == "produce" else "pinned")
        if cls not in ("generated", "free"):
            name = step["output"]
            parts["pinned:" + name] = core._hash_file(core._safe(directory, name))
    return parts


def root(recipe: dict, directory: str | os.PathLike[str]) -> str:
    """Compute the content address of a parsed recipe and its pinned files."""
    preimage = _canonical(_parts(recipe, directory)).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


def build_digest(directory: str | os.PathLike[str]) -> str:
    """Digest the existing, locally generated output files."""
    parsed = recipe_reader.load_recipe(directory)
    entries = []
    for name in recipe_reader.generated_outputs(parsed):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            entries.append([name, core._hash_file(path)])
    entries.sort(key=lambda entry: entry[0])
    return hashlib.sha256(_canonical(entries).encode("utf-8")).hexdigest()
