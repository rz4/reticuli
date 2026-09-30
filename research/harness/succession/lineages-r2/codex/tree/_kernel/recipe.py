"""Read and validate a claim's untrusted recipe.

The parsed TOML is returned without normalization: recipe content participates
in the claim's identity, including fields this layer does not interpret.
"""

from __future__ import annotations

import datetime
import math
import os
import re
import tomllib
from collections.abc import Mapping

from . import core


_MANIFEST_DIGEST = re.compile(r"^[0-9a-f]{64}  (.+)$")


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Find the canonical recipe, falling back to the legacy filename."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.exists(path):
            core._hash_file(path)
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _steps(recipe: Mapping) -> list[dict]:
    """Return steps in declaration order."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("recipe steps must be an array of tables")
    return steps


def gates(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: Mapping) -> list[str]:
    """List generated outputs in recipe order."""
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") in ("generated", "free")]


def _read_input_manifest(directory: os.PathLike[str] | str, name: str) -> list[str]:
    """Read a fixed input list; optional digests annotate, not select, paths."""
    path = core._safe(directory, name)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name}: {exc}") from exc
    names = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _MANIFEST_DIGEST.fullmatch(line)
        entry = match.group(1) if match else line
        if not entry or entry != entry.strip():
            raise core.ClaimError(f"bad inputs manifest entry on line {number}")
        core._safe(directory, entry)
        names.append(entry)
    return names


def _inputs(recipe: Mapping, directory: os.PathLike[str] | str | None = None) -> list[str]:
    """Return declared input names, including the manifest and environment."""
    claim = recipe.get("claim", {})
    if not isinstance(claim, dict):
        raise core.ClaimError("[claim] must be a table")
    names = claim.get("inputs", [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise core.ClaimError("claim inputs must be an array of paths")
    result = list(names)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise core.ClaimError("inputs_manifest must be a path")
        if directory is None:
            raise core.ClaimError("a directory is required to read inputs_manifest")
        result.append(manifest)
        result.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise core.ClaimError("environment must be a path")
        result.append(environment)
    if directory is not None:
        for name in result:
            core._safe(directory, name)
    return result


def _check_json_values(value: object) -> None:
    """Reject TOML values without a stable JSON representation."""
    if isinstance(value, (datetime.date, datetime.time)):
        raise core.ClaimError("TOML date and time values are not supported")
    if isinstance(value, float) and not math.isfinite(value):
        raise core.ClaimError("non-finite recipe number")
    if isinstance(value, dict):
        for member in value.values():
            _check_json_values(member)
    elif isinstance(value, list):
        for member in value:
            _check_json_values(member)


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse a recipe and refuse invalid or hostile content with ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc

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
    _check_json_values(recipe)
    _inputs(recipe, directory)

    for index, step in enumerate(_steps(recipe), 1):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {index} has invalid kind: {kind!r}")
        output = step.get("output")
        core._safe(directory, output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate step {index} requires a run command")
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in ("generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"step {index} has invalid class: {step_class!r}")
    return recipe
