"""Read and validate the untrusted recipe of a claim."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping

from . import core


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def recipe_path(claim_dir: os.PathLike[str] | str) -> str:
    """Locate the canonical recipe, falling back to its older filename."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(claim_dir, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no recipe in {claim_dir}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _path(claim_dir: os.PathLike[str] | str, value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise core.ClaimError(f"{label} must be a nonempty relative path")
    try:
        return core._safe(claim_dir, value)
    except (OSError, ValueError, TypeError) as exc:
        raise core.ClaimError(f"invalid {label}: {value!r}") from exc


def _read_input_manifest(claim_dir: os.PathLike[str] | str,
                         name: str) -> list[str]:
    """Read a fixed input list, optionally checking its embedded digests."""
    path = _path(claim_dir, name, "inputs_manifest")
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as source:
            lines = source.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs_manifest {name}: {exc}") from exc
    names = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest = None
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match:
            digest, entry = match.groups()
        else:
            entry = line
        file_path = _path(claim_dir, entry, f"manifest line {number}")
        actual = core._hash_file(file_path)
        if digest is not None and actual != digest:
            raise core.ClaimError(f"manifest digest mismatch for {entry}")
        names.append(entry)
    return names


def _inputs(recipe: Mapping[str, object],
            claim_dir: os.PathLike[str] | str | None = None) -> list[str]:
    """Return all pinned input names, including the manifest and environment."""
    claim = recipe.get("claim")
    if not isinstance(claim, Mapping):
        raise core.ClaimError("recipe needs a [claim] table")
    declared = claim.get("inputs", [])
    if not isinstance(declared, list) or any(not isinstance(p, str) for p in declared):
        raise core.ClaimError("claim inputs must be a list of paths")
    names = list(declared)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str) or not manifest:
            raise core.ClaimError("inputs_manifest must be a path")
        if claim_dir is None:
            raise core.ClaimError("claim directory required to read inputs_manifest")
        names.append(manifest)
        names.extend(_read_input_manifest(claim_dir, manifest))
    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str) or not environment:
            raise core.ClaimError("environment must be a path")
        names.append(environment)
    if claim_dir is not None:
        for name in names:
            _path(claim_dir, name, "input")
    if len(names) != len(set(names)):
        raise core.ClaimError("duplicate input path")
    return names


def _steps(recipe: Mapping[str, object]) -> list[dict[str, object]]:
    """Return recipe steps in authored order."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("step must be an array of tables")
    return steps


def gates(recipe: Mapping[str, object]) -> list[dict[str, object]]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: Mapping[str, object]) -> list[dict[str, object]]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: Mapping[str, object]) -> list[str]:
    return [step["output"] for step in _steps(recipe)
            if step.get("class", "generated" if step["kind"] == "produce" else "pinned")
            == "generated"]


def load_recipe(claim_dir: os.PathLike[str] | str) -> dict[str, object]:
    """Parse a recipe, converting malformed or hostile input to ClaimError."""
    path = recipe_path(claim_dir)
    core._hash_file(path)
    try:
        with open(path, "rb") as source:
            recipe = tomllib.load(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc
    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe needs a [claim] table")
    if not isinstance(claim.get("name"), str):
        raise core.ClaimError("claim name must be a string")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands (format {core.FORMAT})")
    if "inputs_manifest" in claim and version < 2:
        raise core.ClaimError("inputs_manifest requires claim format 2 or newer")
    _inputs(recipe, claim_dir)
    outputs = set()
    for number, step in enumerate(_steps(recipe), 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {number} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {number} has invalid kind: {kind!r}")
        output = step.get("output")
        _path(claim_dir, output, f"step {number} output")
        if output in outputs:
            raise core.ClaimError(f"duplicate step output: {output}")
        outputs.add(output)
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"step {number} has invalid class: {step_class!r}")
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError(f"gate step {number} needs a run command")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {number} {key} must be a string")
    return recipe
