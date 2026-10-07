"""Read and validate a claim's untrusted recipe."""

from __future__ import annotations

import json
import os
import re
import tomllib

from . import core


_MANIFEST_ENTRY = re.compile(r"([0-9a-f]{64})  (.+)\Z")


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Return the preferred recipe filename present in a claim directory."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError(f"no {core.RECIPE} or {core.LEGACY_RECIPE} in {directory}")


def _steps(recipe: dict) -> list[dict]:
    return recipe.get("step", [])


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, with optional SHA-256 annotations."""
    path = core._safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as source:
            lines = source.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc

    names = []
    for number, line in enumerate(lines, 1):
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.fullmatch(item)
        input_name = match.group(2) if match else item
        try:
            input_path = core._safe(directory, input_name)
        except core.ClaimError as exc:
            raise core.ClaimError(f"inputs manifest line {number}: {exc}") from exc
        if match and core._hash_file(input_path) != match.group(1):
            raise core.ClaimError(
                f"inputs manifest line {number}: digest mismatch for {input_name!r}")
        names.append(input_name)
    return names


def _inputs(recipe: dict, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """Return declared pinned inputs, including the manifest and environment."""
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("claim directory required for inputs_manifest")
        names.append(manifest)
        names.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def _json_value(value: object) -> bool:
    """Check that TOML did not introduce date/time values JSON cannot name."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item)
                   for key, item in value.items())
    return False


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse a recipe, reporting invalid content as ``ClaimError``."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as source:
            recipe = tomllib.load(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc

    if not isinstance(recipe, dict) or not _json_value(recipe):
        raise core.ClaimError("recipe contains unsupported values")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe steps must be an array")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {number} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {number} has invalid kind: {kind!r}")
        core._safe(directory, step.get("output"))
        if "class" in step and step["class"] not in (
                "generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"step {number} has invalid class")
        if kind == "gate" and (not isinstance(step.get("run"), str)
                               or not step["run"]):
            raise core.ClaimError(f"gate step {number} needs a run command")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError(f"step {number} has invalid from")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {number} has invalid {key}")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(n, str) for n in inputs):
        raise core.ClaimError("claim inputs must be an array of paths")
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            core._safe(directory, claim[key])
    for name in _inputs(recipe, directory):
        core._safe(directory, name)

    # json.dumps is also the identity encoder; ensure no non-finite float
    # enters a preimage through TOML's inf/nan syntax.
    try:
        json.dumps(recipe, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"recipe cannot be serialized: {exc}") from exc
    return recipe
