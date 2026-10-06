"""Read and validate the untrusted recipe of a claim."""

from __future__ import annotations

import math
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from . import core


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Return the preferred existing recipe name in *directory*."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.exists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _read_input_manifest(directory: os.PathLike[str] | str, name: str) -> list[str]:
    """Read a fixed input list; optional digest prefixes are checked later by identity."""
    path = core._safe(directory, name)
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc

    inputs: list[str] = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^[0-9a-fA-F]{64}  ", line):
            line = line[66:]
        elif re.match(r"^[0-9a-fA-F]{64}\s", line):
            raise core.ClaimError(f"invalid digest entry at {name}:{number}")
        if not line or line != line.strip():
            raise core.ClaimError(f"invalid input at {name}:{number}")
        core._safe(directory, line)
        inputs.append(line)
    return inputs


def _inputs(recipe: dict[str, Any], directory: os.PathLike[str] | str | None = None) -> list[str]:
    """Return every declared input, including automatic pinned inputs."""
    claim = recipe.get("claim", {})
    declared = claim.get("inputs", [])
    if not isinstance(declared, list) or any(not isinstance(p, str) for p in declared):
        raise core.ClaimError("claim.inputs must be a list of paths")
    inputs = list(declared)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("inputs_manifest requires a claim directory")
        inputs.append(manifest)
        inputs.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        inputs.append(environment)
    if directory is not None:
        for name in inputs:
            core._safe(directory, name)
    return list(dict.fromkeys(inputs))


def _steps(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Return steps in the order declared by the recipe."""
    return recipe.get("step", [])


def gates(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict[str, Any]) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def _number(value: Any, label: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise core.ClaimError(f"{label} must be a finite number")
    if value <= 0 if positive else value < 0:
        raise core.ClaimError(f"{label} must be {'positive' if positive else 'nonnegative'}")


def _validate(recipe: Any, directory: os.PathLike[str] | str) -> None:
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe needs a [claim] table")
    if not isinstance(claim.get("name"), str) or not claim["name"]:
        raise core.ClaimError("claim.name must be a nonempty string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim.format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")
    for field in ("inputs_manifest", "environment"):
        if field in claim:
            core._safe(directory, claim[field])
    _inputs(recipe, directory)
    if "requires" in claim and (not isinstance(claim["requires"], list) or
                                 any(not isinstance(x, str) or not x for x in claim["requires"])):
        raise core.ClaimError("claim.requires must be a list of names")
    for field in ("gate_timeout", "tolerance", "mutation_floor"):
        if field in claim:
            _number(claim[field], f"claim.{field}", positive=field != "mutation_floor")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("claim.envelope must be a nonempty table")
        for unit, limit in envelope.items():
            if unit not in core.COST_UNITS:
                raise core.ClaimError(f"unknown envelope unit: {unit}")
            _number(limit, f"claim.envelope.{unit}", positive=True)

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("step must be an array of tables")
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {index} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {index} has invalid kind: {kind!r}")
        core._safe(directory, step.get("output"))
        classification = step.get("class", "generated" if kind == "produce" else "pinned")
        if classification not in ("generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"step {index} has invalid class: {classification!r}")
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError(f"gate step {index} needs a run command")
        for hint in core.GUIDANCE_KEYS:
            if hint in step and not isinstance(step[hint], str):
                raise core.ClaimError(f"step {index} {hint} must be a string")
        if "from" in step and (not isinstance(step["from"], str) or not step["from"]):
            raise core.ClaimError(f"step {index} from must be a name")


def load_recipe(directory: os.PathLike[str] | str) -> dict[str, Any]:
    """Parse and validate a claim recipe, reporting bad bytes as ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            parsed = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc
    _validate(parsed, directory)
    return parsed
