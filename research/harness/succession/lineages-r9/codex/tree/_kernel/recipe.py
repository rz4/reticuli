"""Read and validate the untrusted recipe of a claim."""

from __future__ import annotations

import datetime
import os
import re
import tomllib
from collections.abc import Mapping

from . import core


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Return the preferred existing recipe filename in *directory*."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError(f"no {core.RECIPE} or {core.LEGACY_RECIPE} in {directory}")


def _steps(recipe: Mapping[str, object]) -> list[dict]:
    """Return the declared steps in their authoring order."""
    return recipe.get("step", [])


def gates(recipe: Mapping[str, object]) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: Mapping[str, object]) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: Mapping[str, object]) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated" and "from" not in step]


def _read_input_manifest(directory: os.PathLike[str] | str, name: str) -> list[str]:
    """Read the fixed list of paths in an inputs manifest."""
    path = core._safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as source:
            lines = source.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name}: {exc}") from exc
    inputs = []
    for number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if re.match(r"^[0-9a-f]{64}  ", entry):
            entry = entry[66:]
        if not entry or entry != entry.strip():
            raise core.ClaimError(f"bad inputs manifest entry on line {number}")
        core._safe(directory, entry)
        inputs.append(entry)
    return inputs


def _inputs(recipe: Mapping[str, object], directory: os.PathLike[str] | str) -> list[str]:
    """List pinned inputs, including the files that declare the environment and list."""
    claim = recipe["claim"]
    result = list(claim.get("inputs", []))
    if "inputs_manifest" in claim:
        name = claim["inputs_manifest"]
        result.append(name)
        result.extend(_read_input_manifest(directory, name))
    if "environment" in claim:
        result.append(claim["environment"])
    return list(dict.fromkeys(result))


def _json_compatible(value: object) -> bool:
    if isinstance(value, (datetime.date, datetime.time)):
        return False
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    return value is None or isinstance(value, (str, int, float, bool))


def _path(directory: os.PathLike[str] | str, value: object, label: str) -> None:
    if not isinstance(value, str):
        raise core.ClaimError(f"{label} must be a path string")
    core._safe(directory, value)


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse a recipe, reporting malformed or hostile content as ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as source:
            recipe = tomllib.load(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc

    if not isinstance(recipe, dict) or not _json_compatible(recipe):
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

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise core.ClaimError("claim inputs must be a list")
    for name in inputs:
        _path(directory, name, "input")
    for field in ("inputs_manifest", "environment"):
        if field in claim:
            _path(directory, claim[field], field)
    if "requires" in claim and (not isinstance(claim["requires"], list)
                                or not all(isinstance(x, str) for x in claim["requires"])):
        raise core.ClaimError("claim requires must be a list of strings")

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe steps must be a list")
    for step in steps:
        if not isinstance(step, dict):
            raise core.ClaimError("each step must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"unknown step kind: {kind!r}")
        _path(directory, step.get("output"), "step output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError("gate step needs a run command")
        classification = step.get("class", "generated" if kind == "produce" else "pinned")
        if classification not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"unknown step class: {classification!r}")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError("step from must be a string")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {key} must be a string")
    return recipe
