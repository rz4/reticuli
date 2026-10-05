"""Read and validate the untrusted recipe in a claim directory."""

from __future__ import annotations

import math
import os
import re
import tomllib

from . import core


_DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Find the preferred recipe filename in a claim directory."""
    for filename in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, filename)
        if os.path.isfile(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}")


def _steps(recipe: dict) -> list[dict]:
    """Return the declared steps, preserving recipe order."""
    return recipe.get("step", [])


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated"]


def _read_input_manifest(path: os.PathLike[str] | str) -> list[str]:
    """Read a fixed input list, with optional SHA-256 annotations."""
    try:
        lines = open(path, "r", encoding="utf-8").read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {path}: {exc}") from exc
    names = []
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _DIGEST_LINE.fullmatch(line)
        if match:
            line = match.group(2)
        elif re.match(r"^[0-9a-f]{64}\s", line):
            raise core.ClaimError(f"malformed inputs manifest line {number}")
        names.append(line)
    return names


def _inputs(recipe: dict, directory: os.PathLike[str] | str | None = None) -> list[str]:
    """Return declared input names, including automatically pinned files."""
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("inputs_manifest requires a claim directory")
        names.append(manifest)
        names.extend(_read_input_manifest(core._safe(directory, manifest)))
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def _positive_number(value: object) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and value > 0)


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse a recipe; turn malformed or hostile input into ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc

    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe requires a string [claim] name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(x, str) for x in inputs):
        raise core.ClaimError("claim inputs must be a list of paths")
    for key in ("inputs_manifest", "environment"):
        if key in claim and not isinstance(claim[key], str):
            raise core.ClaimError(f"claim {key} must be a path")
    if "inputs_manifest" in claim and version < 2:
        raise core.ClaimError("inputs_manifest requires claim format 2 or later")

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe steps must be an array")
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") not in core.KINDS:
            raise core.ClaimError("step kind must be produce or gate")
        if not isinstance(step.get("output"), str):
            raise core.ClaimError("step output must be a path")
        core._safe(directory, step["output"])
        if step["kind"] == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError("gate step requires a run command")
        if "class" in step and step["class"] not in ("generated", "pinned", "validated"):
            raise core.ClaimError("invalid step class")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {key} must be a string")

    for name in _inputs(recipe, directory):
        core._safe(directory, name)
    if "envelope" in claim:
        envelope = claim["envelope"]
        if (not isinstance(envelope, dict) or not envelope or
                any(unit not in core.COST_UNITS or not _positive_number(value)
                    for unit, value in envelope.items())):
            raise core.ClaimError("claim envelope must give positive cost ceilings")
    return recipe
