"""Read and validate the recipe belonging to a claim."""

from __future__ import annotations

import os
import tomllib
from typing import Any

from . import core


def recipe_path(root: str) -> str:
    """Find the current recipe name, falling back to the legacy name."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(root, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError(f"recipe not found in {root!r}")


def _path(root: str, value: Any) -> None:
    """Check that a recipe path stays inside its claim."""
    try:
        core._safe(root, value)
    except (OSError, ValueError, TypeError) as exc:
        raise core.ClaimError(f"invalid claim path: {value!r}") from exc


def _inputs(data: dict[str, Any]) -> list[str]:
    """Return the claim's declared input paths."""
    claim = data.get("claim", {})
    inputs = claim.get("inputs", []) if isinstance(claim, dict) else []
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise core.ClaimError("claim inputs must be a list of paths")
    return inputs


def _read_input_manifest(root: str) -> list[str]:
    """Read the input list from the recipe in *root*."""
    return _inputs(load_recipe(root))


def _steps(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the recipe steps in declaration order."""
    steps = data.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("recipe steps must be tables")
    return steps


def gates(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in _steps(data) if step.get("kind") == "gate"]


def produces(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in _steps(data) if step.get("kind") == "produce"]


def generated_outputs(data: dict[str, Any]) -> list[str]:
    return [step["output"] for step in produces(data) if step.get("class") == "generated"]


def load_recipe(root: str) -> dict[str, Any]:
    """Load a recipe, reporting malformed or unsafe data as ClaimError."""
    try:
        with open(recipe_path(root), "rb") as source:
            data = tomllib.load(source)
    except core.ClaimError:
        raise
    except (OSError, ValueError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe: {exc}") from exc

    if not isinstance(data, dict):
        raise core.ClaimError("recipe must be a table")
    claim = data.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str) or not claim["name"]:
        raise core.ClaimError("recipe requires a claim name")
    for item in _inputs(data):
        _path(root, item)
    for step in _steps(data):
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise core.ClaimError(f"unknown step kind: {kind!r}")
        _path(root, step.get("output"))
        expected_class = "generated" if kind == "produce" else "validated"
        if step.get("class") != expected_class:
            raise core.ClaimError(f"{kind} step requires class {expected_class!r}")
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError("gate step requires a run command")
        if kind == "produce" and "request" in step and not isinstance(step["request"], str):
            raise core.ClaimError("produce request must be text")
    return data
