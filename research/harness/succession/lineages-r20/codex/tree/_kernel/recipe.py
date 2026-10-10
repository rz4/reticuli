"""Read and validate a claim's untrusted recipe.

The returned mapping retains the TOML values and step order.  Identity
canonicalization belongs to the identity layer, not to the recipe reader.
"""

from __future__ import annotations

import os
import re
import tomllib

from . import core


_MANIFEST_ENTRY = re.compile(r"([0-9a-f]{64})  (.+)")


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Return the preferred recipe name, accepting the older name as well."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            core._hash_file(path)  # Reject aliases and non-regular files.
            return path
    raise core.ClaimError(f"no recipe in {directory}: expected {core.RECIPE} or {core.LEGACY_RECIPE}")


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, optionally annotated with SHA-256 hashes."""
    path = core._safe(directory, name)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.read().splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc

    entries = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _MANIFEST_ENTRY.fullmatch(line)
        item = match.group(2) if match else line
        if not match and re.match(r"[0-9a-f]{64}\s", line):
            raise core.ClaimError(f"invalid inputs manifest entry on line {number}")
        core._safe(directory, item)
        entries.append(item)
    return entries


def _inputs(recipe: dict, directory: str | os.PathLike[str] | None = None) -> list[str]:
    """List declared inputs, including the manifest and environment file."""
    claim = recipe.get("claim", {})
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(x, str) for x in inputs):
        raise core.ClaimError("claim inputs must be an array of paths")
    names = list(inputs)
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise core.ClaimError("inputs_manifest must be a path")
        if directory is None:
            raise core.ClaimError("a directory is required to read inputs_manifest")
        names.append(manifest)
        names.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise core.ClaimError("environment must be a path")
        names.append(environment)
    if directory is not None:
        for name in names:
            core._safe(directory, name)
    return names


def _steps(recipe: dict) -> list[dict]:
    """Return recipe steps in their written order."""
    steps = recipe.get("step", [])
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
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
    """Parse a recipe, raising ClaimError for malformed or hostile content."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"cannot parse recipe {path}: {exc}") from exc

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

    _inputs(recipe, directory)
    for index, step in enumerate(_steps(recipe), 1):
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {index} has invalid kind: {kind!r}")
        output = step.get("output")
        core._safe(directory, output)
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"gate step {index} needs a run command")
        cls = step.get("class", "generated" if kind == "produce" else "pinned")
        if cls not in ("generated", "pinned", "validated", "free", "exact"):
            raise core.ClaimError(f"step {index} has invalid class: {cls!r}")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError(f"step {index} has invalid from value")
    return recipe
