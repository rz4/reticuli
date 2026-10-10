"""Read and validate the untrusted recipe of a claim."""

from __future__ import annotations

import os
import re
import tomllib

from . import core


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Return the preferred recipe path, accepting the historical filename."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}")


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, optionally prefixed by SHA-256 digests."""
    path = core._safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    inputs = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        entry = match.group(2) if match else line
        if not entry or entry.startswith("#"):
            raise core.ClaimError(f"invalid manifest entry at line {number}")
        core._safe(directory, entry)
        inputs.append(entry)
    return inputs


def _inputs(recipe: dict, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """List the declared inputs, including the manifest and environment file."""
    claim = recipe.get("claim", {})
    listed = claim.get("inputs", [])
    if not isinstance(listed, list) or any(not isinstance(p, str) for p in listed):
        raise core.ClaimError("claim inputs must be an array of paths")
    inputs = list(listed)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise core.ClaimError("inputs_manifest must be a path")
        if directory is None:
            raise core.ClaimError("inputs_manifest needs a claim directory")
        inputs.append(manifest)
        inputs.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise core.ClaimError("environment must be a path")
        inputs.append(environment)
    if directory is not None:
        for name in inputs:
            core._safe(directory, name)
    return list(dict.fromkeys(inputs))


def _steps(recipe: dict) -> list[dict]:
    """Return steps in the order written in the recipe."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("step must be an array of tables")
    return steps


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse a claim recipe; report every invalid declaration as ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc

    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe needs [claim] name as a string")
    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    _inputs(recipe, directory)
    for step in _steps(recipe):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"invalid step kind: {kind!r}")
        core._safe(directory, step.get("output"))
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError("gate step needs a run command")
        klass = step.get("class", "generated" if kind == "produce" else "pinned")
        if klass not in ("generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"invalid step class: {klass!r}")
    return recipe
