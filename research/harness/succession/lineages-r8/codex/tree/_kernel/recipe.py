"""Read and validate a claim's untrusted TOML recipe.

The parsed document is kept intact: defaults and manifest entries are resolved by
the accessors, so neither operation silently changes the identity preimage.
"""

from __future__ import annotations

import math
import os
import re
import tomllib
from pathlib import Path

from . import core


_MANIFEST_ENTRY = re.compile(r"[0-9a-fA-F]{64}  (.+)\Z")
_CLASSES = frozenset({"generated", "pinned", "validated", "free", "exact"})


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Choose the canonical recipe name, falling back to the legacy name."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            return path
    raise core.ClaimError(f"no {core.RECIPE} or {core.LEGACY_RECIPE} in {directory}")


def _steps(recipe: dict) -> list[dict]:
    """Return the steps in their declared order."""
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
            if step.get("class", "generated") in ("generated", "free")]


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, optionally prefixed by SHA-256 digests."""
    path = core._safe(directory, name)
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    entries = []
    for number, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.fullmatch(line)
        entry = match.group(1) if match else line
        if not entry or entry != entry.strip():
            raise core.ClaimError(f"invalid inputs manifest entry at line {number}")
        core._safe(directory, entry)
        entries.append(entry)
    return entries


def _inputs(recipe: dict, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """Return explicit and manifest inputs, including the manifest itself."""
    claim = recipe.get("claim", {})
    names = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if directory is None:
            raise core.ClaimError("claim directory required to read inputs_manifest")
        names.append(manifest)
        names.extend(_read_input_manifest(directory, manifest))
    return names


def _json_compatible(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_compatible(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_compatible(item)
                   for key, item in value.items())
    return False


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse and validate a claim recipe; report bad input as ClaimError."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot read recipe {path}: {exc}") from exc

    if not isinstance(recipe, dict) or not _json_compatible(recipe):
        raise core.ClaimError("recipe contains values without a canonical JSON form")
    claim = recipe.get("claim")
    if not isinstance(claim, dict) or not isinstance(claim.get("name"), str):
        raise core.ClaimError("recipe needs a [claim] table with a string name")
    version = claim.get("format", 1)
    if type(version) is not int or version < 1:
        raise core.ClaimError("claim format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it")

    names = claim.get("inputs", [])
    if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
        raise core.ClaimError("claim inputs must be an array of paths")
    for name in names:
        core._safe(directory, name)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if version < 2 or not isinstance(manifest, str):
            raise core.ClaimError("inputs_manifest requires format 2 and a path")
        core._safe(directory, manifest)
        _read_input_manifest(directory, manifest)
    environment = claim.get("environment")
    if environment is not None:
        core._safe(directory, environment)

    seen = set()
    for step in _steps(recipe):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"unknown step kind: {kind!r}")
        output = step.get("output")
        core._safe(directory, output)
        if output in seen:
            raise core.ClaimError(f"duplicate step output: {output!r}")
        seen.add(output)
        step_class = step.get("class", "generated" if kind == "produce" else "pinned")
        if step_class not in _CLASSES:
            raise core.ClaimError(f"unknown step class: {step_class!r}")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate {output!r} needs a run command")
    return recipe
