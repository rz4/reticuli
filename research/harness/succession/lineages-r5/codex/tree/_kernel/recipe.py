"""Read and validate a claim's untrusted recipe."""

from __future__ import annotations

import os
import re
import tomllib

from . import core


def recipe_path(directory: str) -> str:
    """Find the preferred recipe name, retaining support for older claims."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _declared_path(directory: str, name: str) -> str:
    """Check a recipe path, including exact spelling on case-folding hosts."""
    path = core._safe(directory, name)
    current = os.path.realpath(directory)
    for part in name.split("/"):
        if os.path.isdir(current):
            try:
                entries = os.listdir(current)
            except OSError as exc:
                raise core.ClaimError(f"cannot inspect claim path {name!r}: {exc}") from exc
            if part not in entries and any(entry.casefold() == part.casefold() for entry in entries):
                raise core.ClaimError(f"claim path case does not match directory entry: {name!r}")
        current = os.path.join(current, part)
    return path


def _steps(recipe: dict) -> list[dict]:
    """Return steps in recipe order."""
    return recipe.get("step", [])


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated" and "from" not in step]


def _read_input_manifest(directory: str, name: str) -> list[str]:
    """Read a fixed input list; optional SHA-256 prefixes are checked."""
    path = _declared_path(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc

    inputs = []
    for line_number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", entry)
        if match:
            digest, item = match.groups()
        else:
            digest, item = None, entry
        _declared_path(directory, item)
        if digest is not None and core._hash_file(core._safe(directory, item)) != digest:
            raise core.ClaimError(f"inputs manifest hash mismatch for {item!r} on line {line_number}")
        inputs.append(item)
    return inputs


def _inputs(recipe: dict, directory: str) -> list[str]:
    """List pinned inputs, including manifest and environment files."""
    claim = recipe["claim"]
    result = list(claim.get("inputs", []))
    if "inputs_manifest" in claim:
        name = claim["inputs_manifest"]
        result.append(name)
        result.extend(_read_input_manifest(directory, name))
    if "environment" in claim:
        result.append(claim["environment"])
    return list(dict.fromkeys(result))


def load_recipe(directory: str) -> dict:
    """Parse a recipe and turn all malformed or hostile input into ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc

    if not isinstance(recipe, dict) or not isinstance(recipe.get("claim"), dict):
        raise core.ClaimError("recipe needs a [claim] table")
    claim = recipe["claim"]
    if not isinstance(claim.get("name"), str):
        raise core.ClaimError("[claim] name must be a string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    if "inputs" in claim and (not isinstance(claim["inputs"], list) or
                              any(not isinstance(item, str) for item in claim["inputs"])):
        raise core.ClaimError("[claim] inputs must be an array of paths")
    for key in ("inputs_manifest", "environment"):
        if key in claim and not isinstance(claim[key], str):
            raise core.ClaimError(f"[claim] {key} must be a path string")
    for item in _inputs(recipe, directory):
        _declared_path(directory, item)

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("[[step]] must be an array of tables")
    seen = set()
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {index} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {index} has invalid kind: {kind!r}")
        output = step.get("output")
        if not isinstance(output, str):
            raise core.ClaimError(f"step {index} needs an output path")
        _declared_path(directory, output)
        if output in seen:
            raise core.ClaimError(f"duplicate step output: {output!r}")
        seen.add(output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate step {index} needs a run command")
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"step {index} has invalid class: {step_class!r}")
        if "from" in step and (kind != "produce" or not isinstance(step["from"], str)):
            raise core.ClaimError(f"step {index} has invalid from value")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {index} {key} must be a string")
    return recipe
