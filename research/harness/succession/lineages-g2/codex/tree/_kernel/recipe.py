"""Read and validate a claim recipe without trusting its on-disk bytes."""

from __future__ import annotations

import datetime
import math
import os
import re
import tomllib
from collections.abc import Mapping

from . import core


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Return the preferred recipe filename, accepting the older name."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _steps(recipe: Mapping) -> list[dict]:
    """Return steps in authoring order, including both kinds."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise core.ClaimError("recipe step must be an array of tables")
    return steps


def gates(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: Mapping) -> list[str]:
    return [step["output"] for step in _steps(recipe)
            if step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
            in ("generated", "free")]


def _read_input_manifest(directory: os.PathLike[str] | str, name: str) -> list[str]:
    """Read a fixed input list, with optional SHA-256 annotations."""
    path = core._safe(directory, name)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name}: {exc}") from exc
    result = []
    for number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", entry)
        if match:
            entry = match.group(2)
        elif re.match(r"[0-9a-fA-F]{64}\s", entry):
            raise core.ClaimError(f"invalid inputs manifest entry on line {number}")
        core._safe(directory, entry)
        result.append(entry)
    return result


def _inputs(recipe: Mapping, directory: os.PathLike[str] | str | None = None) -> list[str]:
    """Return declared inputs, including the manifest and environment file."""
    claim = recipe.get("claim", {})
    if not isinstance(claim, dict):
        raise core.ClaimError("[claim] must be a table")
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(p, str) for p in inputs):
        raise core.ClaimError("claim inputs must be an array of paths")
    result = list(inputs)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("inputs_manifest requires a claim directory")
        result.append(manifest)
        result.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        result.append(environment)
    return list(dict.fromkeys(result))


def _positive_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _validate(recipe: object, directory: os.PathLike[str] | str) -> None:
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe requires a [claim] table")
    if not isinstance(claim.get("name"), str):
        raise core.ClaimError("claim name must be a string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            core._safe(directory, claim[key])
    for path in _inputs(recipe, directory):
        core._safe(directory, path)
    if "requires" in claim and (not isinstance(claim["requires"], list) or
                                any(not isinstance(x, str) for x in claim["requires"])):
        raise core.ClaimError("claim requires must be an array of strings")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope or any(
                key not in core.COST_UNITS or not _positive_number(value)
                for key, value in envelope.items()):
            raise core.ClaimError("claim envelope must contain positive cost ceilings")
    for key in ("gate_timeout", "tolerance"):
        if key in claim and not _positive_number(claim[key]):
            raise core.ClaimError(f"claim {key} must be a positive number")
    if "mutation_floor" in claim and not (type(claim["mutation_floor"]) in (int, float)
                                         and 0 <= claim["mutation_floor"] <= 1):
        raise core.ClaimError("claim mutation_floor must be between zero and one")
    seen = set()
    for step in _steps(recipe):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"invalid step kind: {kind!r}")
        output = step.get("output")
        core._safe(directory, output)
        if output in seen:
            raise core.ClaimError(f"duplicate step output: {output}")
        seen.add(output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate {output} requires a run command")
        cls = step.get("class", "generated" if kind == "produce" else "pinned")
        if cls not in ("generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"invalid step class: {cls!r}")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {output} {key} must be a string")
    # TOML dates and times have no representation in the canonical JSON preimage.
    def check_json(value: object) -> None:
        if isinstance(value, (datetime.date, datetime.time)):
            raise core.ClaimError("TOML dates and times are not valid recipe values")
        if isinstance(value, dict):
            for child in value.values():
                check_json(child)
        elif isinstance(value, list):
            for child in value:
                check_json(child)
    check_json(recipe)


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse a claim recipe; report malformed or hostile input as ClaimError."""
    try:
        path = recipe_path(directory)
        core._hash_file(path)
        with open(path, "rb") as stream:
            parsed = tomllib.load(stream)
        _validate(parsed, directory)
        return parsed
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot load recipe in {directory}: {exc}") from exc
