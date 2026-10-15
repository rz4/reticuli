"""Kernel recipe parsing, validation, and query operations."""

import datetime
import os
import tomllib
from typing import Any

from reticuli._kernel import core

__all__ = [
    "_inputs",
    "_read_input_manifest",
    "_steps",
    "gates",
    "generated_outputs",
    "load_recipe",
    "produces",
    "recipe_path",
]


def _check_no_datetime(val: Any) -> None:
    """Refuse TOML date and time values recursively."""
    if isinstance(val, (datetime.date, datetime.time, datetime.datetime)):
        raise core.ClaimError("TOML date and time values are refused")
    if isinstance(val, dict):
        for k, v in val.items():
            _check_no_datetime(k)
            _check_no_datetime(v)
    elif isinstance(val, list):
        for item in val:
            _check_no_datetime(item)


def recipe_path(d: str) -> str:
    """Find the path to the recipe file in directory d, preferring reticuli.toml."""
    if not isinstance(d, str) or not d:
        raise core.ClaimError("Empty or invalid claim directory")
    if os.path.isfile(d):
        if os.path.islink(d):
            raise core.ClaimError(f"Symlinks are not allowed: {d}")
        return d
    if os.path.isdir(d):
        for candidate in (core.RECIPE, core.LEGACY_RECIPE):
            target = os.path.join(d, candidate)
            if os.path.exists(target):
                if os.path.islink(target):
                    raise core.ClaimError(f"Symlinks are not allowed: {target}")
                if os.path.isfile(target):
                    return target
        raise core.ClaimError(f"No recipe found in {d}")
    raise core.ClaimError(f"Directory or recipe does not exist: {d}")


def load_recipe(d: str) -> dict:
    """Read, parse, and validate a claim recipe from directory or file d."""
    path = recipe_path(d)
    claim_dir = d if os.path.isdir(d) else os.path.dirname(os.path.abspath(path))

    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise core.ClaimError(f"Cannot read recipe {path}: {e}")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise core.ClaimError(f"Recipe is not valid UTF-8: {e}")

    try:
        data = tomllib.loads(text)
    except Exception as e:
        raise core.ClaimError(f"Malformed recipe TOML: {e}")

    _check_no_datetime(data)

    if not isinstance(data, dict):
        raise core.ClaimError("Recipe must be a table")

    if "claim" in data and "record" in data:
        raise core.ClaimError("Recipe cannot specify both [claim] and [record]")
    if "claim" not in data:
        if "record" in data:
            data["claim"] = data.pop("record")
        else:
            raise core.ClaimError("Recipe missing [claim] section")

    claim = data["claim"]
    if not isinstance(claim, dict):
        raise core.ClaimError("[claim] must be a table")

    name = claim.get("name")
    if not isinstance(name, str) or not name:
        raise core.ClaimError("[claim] 'name' is required and must be a non-empty string")

    if "format" in claim:
        fmt = claim["format"]
        if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
            raise core.ClaimError(f"claim format must be a positive integer, got {fmt!r}")
        if fmt > core.FORMAT:
            raise core.ClaimError(
                f"claim format {fmt} is newer than this kernel understands "
                f"(format {core.FORMAT}); upgrade reticuli to read it"
            )

    if "inputs" in claim:
        inputs = claim["inputs"]
        if not isinstance(inputs, list):
            raise core.ClaimError("[claim] 'inputs' must be a list")
        for inp in inputs:
            if not isinstance(inp, str) or not inp:
                raise core.ClaimError(f"Invalid input path: {inp!r}")
            core._safe(claim_dir, inp)

    if "inputs_manifest" in claim:
        im = claim["inputs_manifest"]
        if not isinstance(im, str) or not im:
            raise core.ClaimError("[claim] 'inputs_manifest' must be a non-empty string")
        core._safe(claim_dir, im)

    if "environment" in claim:
        env = claim["environment"]
        if not isinstance(env, str) or not env:
            raise core.ClaimError("[claim] 'environment' must be a non-empty string")
        core._safe(claim_dir, env)

    if "requires" in claim:
        req = claim["requires"]
        if not isinstance(req, list) or not all(isinstance(x, str) for x in req):
            raise core.ClaimError("[claim] 'requires' must be a list of strings")

    if "gate_timeout" in claim:
        gt = claim["gate_timeout"]
        if isinstance(gt, bool) or not isinstance(gt, (int, float)) or gt <= 0:
            raise core.ClaimError("[claim] 'gate_timeout' must be a positive number")

    if "mutation_floor" in claim:
        mf = claim["mutation_floor"]
        if isinstance(mf, bool) or not isinstance(mf, (int, float)) or mf < 0:
            raise core.ClaimError("[claim] 'mutation_floor' must be a non-negative number")

    if "tolerance" in claim:
        tol = claim["tolerance"]
        if isinstance(tol, bool) or not isinstance(tol, (int, float)) or tol < 0:
            raise core.ClaimError("[claim] 'tolerance' must be a non-negative number")

    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("[claim] 'envelope' must be a non-empty table")
        for unit, val in envelope.items():
            if unit not in core.COST_KEYS:
                raise core.ClaimError(f"Unknown envelope cost unit: {unit!r}")
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
                raise core.ClaimError(f"Envelope ceiling for {unit} must be a positive number")

    steps = data.get("step")
    if steps is None and "steps" in data:
        steps = data["steps"]
        data["step"] = data.pop("steps")

    if steps is not None:
        if not isinstance(steps, list):
            raise core.ClaimError("Recipe steps must be an array of tables")
        for step in steps:
            if not isinstance(step, dict):
                raise core.ClaimError("Step must be a table")
            kind = step.get("kind")
            if kind not in core.KINDS:
                raise core.ClaimError(f"Invalid or missing step kind: {kind!r}")
            output = step.get("output")
            if not isinstance(output, str) or not output:
                raise core.ClaimError("Step 'output' is required and must be a non-empty string")
            core._safe(claim_dir, output)

            if kind == "gate":
                run = step.get("run")
                if not isinstance(run, str) or not run:
                    raise core.ClaimError("Gate step requires a non-empty 'run' command string")

            cls = step.get("class")
            if cls is not None:
                if cls not in ("generated", "pinned", "validated", "free", "exact"):
                    raise core.ClaimError(f"Invalid step class: {cls!r}")
            else:
                step["class"] = "generated" if kind == "produce" else "pinned"

            if "guidance" in step and not isinstance(step["guidance"], str):
                raise core.ClaimError("Step guidance must be a string")
            if "request" in step and not isinstance(step["request"], str):
                raise core.ClaimError("Step request must be a string")
            if "from" in step and (not isinstance(step["from"], str) or not step["from"]):
                raise core.ClaimError("Step 'from' must be a non-empty string")

    return data


def _steps(recipe: dict) -> list[dict]:
    """Return the steps array from the parsed recipe, preserving order."""
    if not isinstance(recipe, dict):
        return []
    steps = recipe.get("step")
    if steps is None:
        steps = recipe.get("steps", [])
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def gates(recipe: dict) -> list[dict]:
    """Return all gate steps in the recipe."""
    return [s for s in _steps(recipe) if s.get("kind") == "gate"]


def produces(recipe: dict) -> list[dict]:
    """Return all produce steps in the recipe."""
    return [s for s in _steps(recipe) if s.get("kind") == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    """Return output paths for all generated (regrowable) steps in the recipe."""
    outputs = []
    for step in _steps(recipe):
        cls = step.get("class")
        if cls is None and step.get("kind") == "produce":
            cls = "generated"
        if cls in ("generated", "free"):
            outputs.append(step["output"])
    return outputs


def _read_input_manifest(d: str, manifest: str | None = None) -> list[str]:
    """Read a format-2 inputs manifest file and return the list of relative paths."""
    if manifest is None:
        filepath = d
        claim_dir = os.path.dirname(os.path.abspath(d)) or "."
    else:
        claim_dir = d
        filepath = core._safe(d, manifest)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise core.ClaimError(f"Cannot read inputs manifest: {e}")

    paths: list[str] = []
    seen: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64 and all(c in "0123456789abcdefABCDEF" for c in parts[0]):
            p = parts[1].strip()
        else:
            p = line

        resolved = core._safe(claim_dir, p)
        if not os.path.exists(resolved):
            raise core.ClaimError(f"Input manifest names missing file: {p}")

        if p not in seen:
            seen.add(p)
            paths.append(p)

    return paths


def _inputs(recipe: dict | str, d: str | None = None) -> list[str]:
    """Return the ordered, deduplicated list of pinned inputs for a recipe."""
    if isinstance(recipe, str):
        d = recipe
        recipe = load_recipe(d)

    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    inputs: list[str] = []
    seen: set[str] = set()

    def _add(p: str) -> None:
        if p not in seen:
            seen.add(p)
            inputs.append(p)

    for p in claim.get("inputs", []):
        _add(p)

    if "inputs_manifest" in claim:
        manifest_rel = claim["inputs_manifest"]
        _add(manifest_rel)
        if d is not None:
            for p in _read_input_manifest(d, manifest_rel):
                _add(p)

    if "environment" in claim:
        _add(claim["environment"])

    return inputs
