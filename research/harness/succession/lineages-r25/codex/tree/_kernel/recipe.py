"""Read and validate a claim's untrusted TOML recipe.

The parsed mapping is left intact: adding defaults to it would change the
canonical recipe used for a claim's identity.
"""

from __future__ import annotations

import math
import os
import re
import tomllib
from collections.abc import Mapping

from . import core


_MANIFEST_ENTRY = re.compile(r"([0-9a-f]{64})  (.+)")
_CLASSES = frozenset(("generated", "pinned", "validated"))


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Choose the canonical recipe name, accepting the older name as well."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = os.path.join(directory, name)
        if os.path.lexists(path):
            core._hash_file(path)
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _steps(recipe: Mapping) -> list[dict]:
    """Return the step array in authoring order."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("recipe step must be an array of tables")
    return steps


def gates(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: Mapping) -> list[dict]:
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: Mapping) -> list[str]:
    """Names of locally generated produce outputs."""
    return [step["output"] for step in produces(recipe)
            if step.get("class", "generated") == "generated" and "from" not in step]


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, checking any digests carried by its entries."""
    path = core._safe(directory, name)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name}: {exc}") from exc

    names: list[str] = []
    for number, line in enumerate(lines, 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.fullmatch(entry)
        digest, declared = (match.group(1), match.group(2)) if match else (None, entry)
        if declared != declared.strip() or not declared:
            raise core.ClaimError(f"invalid inputs manifest entry at line {number}")
        file_path = core._safe(directory, declared)
        actual = core._hash_file(file_path)
        if digest is not None and actual != digest:
            raise core.ClaimError(f"inputs manifest digest mismatch for {declared}")
        names.append(declared)
    return names


def _inputs(recipe: Mapping, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """Declared input paths, including the manifest and environment file."""
    claim = recipe.get("claim", {})
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("claim directory needed to read inputs_manifest")
        names.append(manifest)
        names.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None and environment not in names:
        names.append(environment)
    return names


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise core.ClaimError(f"{label} must be a finite number")
    if positive and value <= 0:
        raise core.ClaimError(f"{label} must be positive")


def _validate(recipe: object, directory: str | os.PathLike[str]) -> None:
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe needs [claim] with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands (format {core.FORMAT}); "
            "upgrade reticuli to read it")

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise core.ClaimError("claim inputs must be an array of paths")
    for name in inputs:
        core._safe(directory, name)
    for field in ("inputs_manifest", "environment"):
        if field in claim:
            core._safe(directory, claim[field])
    if "inputs_manifest" in claim:
        _read_input_manifest(directory, claim["inputs_manifest"])
    requires = claim.get("requires", [])
    if not isinstance(requires, list) or any(not isinstance(item, str) for item in requires):
        raise core.ClaimError("claim requires must be an array of strings")
    for field in ("gate_timeout", "tolerance"):
        if field in claim:
            _number(claim[field], field, positive=True)
    if "mutation_floor" in claim:
        _number(claim["mutation_floor"], "mutation_floor")
        if not 0 <= claim["mutation_floor"] <= 1:
            raise core.ClaimError("mutation_floor must be between zero and one")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("envelope must be a nonempty table")
        for unit, limit in envelope.items():
            if unit not in core.COST_UNITS:
                raise core.ClaimError(f"unknown envelope unit: {unit}")
            _number(limit, f"envelope {unit}", positive=True)

    for step in _steps(recipe):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"invalid step kind: {kind!r}")
        core._safe(directory, step.get("output"))
        default_class = "generated" if kind == "produce" else "pinned"
        if step.get("class", default_class) not in _CLASSES:
            raise core.ClaimError(f"invalid step class: {step.get('class')!r}")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError("gate step needs a run command")
        if "from" in step and (kind != "produce" or not isinstance(step["from"], str)):
            raise core.ClaimError("step from must name a component on a produce step")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {key} must be a string")


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse a claim recipe, raising ClaimError for malformed or hostile input."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc
    _validate(recipe, directory)
    return recipe
