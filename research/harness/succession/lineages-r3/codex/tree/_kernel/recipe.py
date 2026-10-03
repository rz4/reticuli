"""Read and validate the untrusted recipe of a claim."""

from __future__ import annotations

import datetime
import math
import os
import re
import stat
import tomllib

from . import core


_CLASSES = frozenset({"generated", "pinned", "validated", "free", "exact"})
_SHA_LINE = re.compile(r"^[0-9a-f]{64}  (.+)$")


def recipe_path(directory: os.PathLike[str] | str) -> str:
    """Return the canonical recipe path, accepting the old filename as fallback."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = os.path.join(directory, name)
        if os.path.lexists(path):
            return core._safe(directory, name)
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _steps(recipe: dict) -> list[dict]:
    """Return steps in declaration order."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("recipe step must be an array of tables")
    return steps


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") in ("generated", "free")
            and "from" not in step]


def _read_input_manifest(directory: os.PathLike[str] | str, name: str) -> list[str]:
    """Read a fixed input list, optionally prefixed by SHA-256 digests."""
    path = core._safe(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    result = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matched = _SHA_LINE.fullmatch(line)
        if matched:
            line = matched.group(1)
        elif re.match(r"^[0-9a-f]{64}\s", line):
            raise core.ClaimError(f"malformed inputs manifest line {number}")
        core._safe(directory, line)
        result.append(line)
    return result


def _inputs(recipe: dict, directory: os.PathLike[str] | str) -> list[str]:
    """Return all pinned input names, including manifest and environment."""
    claim = recipe.get("claim", {})
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        names.append(manifest)
        names.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)
    for name in names:
        core._safe(directory, name)
    return names


def _json_compatible(value: object) -> bool:
    if isinstance(value, (datetime.date, datetime.time)):
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    return isinstance(value, (str, int, bool))


def load_recipe(directory: os.PathLike[str] | str) -> dict:
    """Parse a claim recipe; all invalid input is refused with ClaimError."""
    path = recipe_path(directory)
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise core.ClaimError(f"recipe is not a regular singly linked file: {path}")
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc
    if not _json_compatible(recipe):
        raise core.ClaimError("recipe contains a non-JSON value")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe requires [claim] name as a string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(f"claim format {version} is newer than this kernel understands (format {core.FORMAT})")
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(name, str) for name in inputs):
        raise core.ClaimError("claim inputs must be an array of paths")
    for key in ("inputs_manifest", "environment"):
        if key in claim and not isinstance(claim[key], str):
            raise core.ClaimError(f"claim {key} must be a path")
    if "inputs_manifest" in claim and version < 2:
        raise core.ClaimError("inputs_manifest requires claim format 2")
    _inputs(recipe, directory)
    seen = set()
    for step in _steps(recipe):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"invalid step kind: {kind!r}")
        output = step.get("output")
        core._safe(directory, output)
        if output in seen:
            raise core.ClaimError(f"duplicate step output: {output!r}")
        seen.add(output)
        if "class" in step and step["class"] not in _CLASSES:
            raise core.ClaimError(f"invalid step class: {step['class']!r}")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate {output!r} requires a run command")
        for key in ("from",):
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {key} must be a string")
    return recipe
