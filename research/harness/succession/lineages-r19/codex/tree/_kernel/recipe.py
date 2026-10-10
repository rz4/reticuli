"""Read and validate a claim's untrusted TOML recipe."""

from __future__ import annotations

import math
import os
import re
import tomllib
from pathlib import Path

from . import core


_MANIFEST_ENTRY = re.compile(r"([0-9a-f]{64})  (.+)")


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Find the preferred recipe name in a claim directory."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _read_input_manifest(path: os.PathLike[str] | str) -> list[str]:
    """Read the fixed path list in an inputs manifest."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {path}: {exc}") from exc
    names = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.fullmatch(line)
        if match:
            line = match.group(2)
        elif re.match(r"[0-9a-f]{64}\s", line):
            raise core.ClaimError(f"malformed inputs manifest entry on line {number}")
        names.append(line)
    return names


def _inputs(recipe: dict, directory: os.PathLike[str] | str | None = None) -> list[str]:
    """Return declared inputs, including the manifest itself when present."""
    claim = recipe["claim"]
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("an inputs manifest needs a claim directory")
        path = core._safe(directory, manifest)
        names.append(manifest)
        names.extend(_read_input_manifest(path))
    return names


def _steps(recipe: dict) -> list[dict]:
    """Return steps in their authored order."""
    return recipe.get("step", [])


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    """Return generated outputs belonging to this claim."""
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated" and "from" not in step]


def _number(value: object, *, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse and validate a recipe; all bad claim data raises ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc

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
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise core.ClaimError("claim inputs must be a list of paths")
    manifest = claim.get("inputs_manifest")
    if manifest is not None and (version < 2 or not isinstance(manifest, str)):
        raise core.ClaimError("inputs_manifest requires format 2 or newer and a path")
    environment = claim.get("environment")
    if environment is not None and not isinstance(environment, str):
        raise core.ClaimError("claim environment must be a path")
    try:
        for name in _inputs(recipe, directory):
            core._safe(directory, name)
        if environment is not None:
            core._safe(directory, environment)
    except core.ClaimError:
        raise

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe step must be an array")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {number} must be a table")
        kind = step.get("kind")
        if not isinstance(kind, str) or kind not in core.KINDS:
            raise core.ClaimError(f"step {number} has invalid kind: {kind!r}")
        output = step.get("output")
        if not isinstance(output, str):
            raise core.ClaimError(f"step {number} needs an output path")
        core._safe(directory, output)
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"step {number} has invalid class: {step_class!r}")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate step {number} needs a run command")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError(f"step {number} has invalid from value")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {number} has invalid {key}")

    envelope = claim.get("envelope")
    if envelope is not None:
        if (not isinstance(envelope, dict) or not envelope or
                any(key not in core.COST_KEYS or not _number(value, positive=True)
                    for key, value in envelope.items())):
            raise core.ClaimError("claim envelope needs positive cost ceilings")
    return recipe
