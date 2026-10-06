"""Read and validate the recipe of a content-addressed claim."""

from __future__ import annotations

import datetime
import math
import os
import re
import tomllib
from collections.abc import Mapping

from . import core


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Return the preferred recipe name, accepting the legacy name too."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}")


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, with optional SHA-256 annotations."""
    path = core._safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as source:
            lines = source.readlines()
    except (OSError, UnicodeError) as error:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {error}") from error
    paths = []
    for number, line in enumerate(lines, 1):
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", item)
        if match:
            item = match.group(2)
        elif re.match(r"[0-9a-f]{64}\s", item):
            raise core.ClaimError(f"malformed inputs manifest line {number}")
        core._safe(directory, item)
        paths.append(item)
    return paths


def _inputs(recipe: Mapping, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """Return all declared input names, including the manifest and environment."""
    claim = recipe.get("claim", {})
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("inputs_manifest needs a claim directory")
        names.extend(_read_input_manifest(directory, manifest))
        names.append(manifest)
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    return list(dict.fromkeys(names))


def _steps(recipe: Mapping) -> list[dict]:
    """Return steps in recipe order."""
    return recipe.get("step", [])


def gates(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: Mapping) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated"]


def _check_json_value(value: object) -> None:
    """Refuse TOML values that cannot enter a portable JSON preimage."""
    if isinstance(value, (datetime.date, datetime.time)):
        raise core.ClaimError("TOML date and time values are not supported")
    if isinstance(value, float) and not math.isfinite(value):
        raise core.ClaimError("non-finite recipe number")
    if isinstance(value, dict):
        for nested in value.values():
            _check_json_value(nested)
    elif isinstance(value, list):
        for nested in value:
            _check_json_value(nested)


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse an untrusted recipe; report malformed claims with ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as source:
            recipe = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError, UnicodeError) as error:
        raise core.ClaimError(f"cannot read recipe {path}: {error}") from error

    _check_json_value(recipe)
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise core.ClaimError("claim inputs must be a list of paths")
    for item in inputs:
        core._safe(directory, item)
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            core._safe(directory, claim[key])
    if "inputs_manifest" in claim:
        if version < 2:
            raise core.ClaimError("inputs_manifest requires claim format 2")
        _read_input_manifest(directory, claim["inputs_manifest"])

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe steps must be a list")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {index} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {index} has invalid kind: {kind!r}")
        core._safe(directory, step.get("output"))
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError(f"gate step {index} needs a run command")
        default_class = "generated" if kind == "produce" else "pinned"
        if step.get("class", default_class) not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"step {index} has invalid class")
    return recipe
