"""Read and validate a claim's untrusted TOML recipe."""

from __future__ import annotations

import os
import re
import tomllib

from . import core


def recipe_path(directory: str | os.PathLike[str]) -> str:
    """Return the preferred existing recipe name in *directory*."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(directory, name)
        if os.path.lexists(path):
            core._hash_file(path)
            return path
    raise core.ClaimError(f"no {core.RECIPE} or {core.LEGACY_RECIPE} in {directory}")


def _path(directory: str | os.PathLike[str], name: object) -> str:
    return core._safe(directory, name)


def _read_input_manifest(directory: str | os.PathLike[str], name: str) -> list[str]:
    """Read a fixed input list, optionally annotated with SHA-256 digests."""
    path = _path(directory, name)
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            lines = stream.readlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {name!r}: {exc}") from exc
    names = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if match:
            digest, entry = match.groups()
        else:
            digest, entry = None, line
        _path(directory, entry)
        if digest is not None and core._hash_file(_path(directory, entry)) != digest.lower():
            raise core.ClaimError(f"inputs manifest digest mismatch for {entry!r} at line {number}")
        names.append(entry)
    return names


def _inputs(recipe: dict, directory: str | os.PathLike[str]) -> list[str]:
    """Expand declared inputs, including the manifest and environment file."""
    claim = recipe["claim"]
    result = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        result.append(manifest)
        result.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        result.append(environment)
    return list(dict.fromkeys(result))


def _steps(recipe: dict) -> list[dict]:
    return recipe.get("step", [])


def gates(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "gate"]


def produces(recipe: dict) -> list[dict]:
    return [step for step in _steps(recipe) if step["kind"] == "produce"]


def generated_outputs(recipe: dict) -> list[str]:
    return [step["output"] for step in _steps(recipe)
            if step.get("class", "generated" if step["kind"] == "produce" else "pinned") == "generated"]


def _positive_number(value: object) -> bool:
    return type(value) in (int, float) and value > 0


def load_recipe(directory: str | os.PathLike[str]) -> dict:
    """Parse a claim recipe, refusing malformed or unsafe declarations."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            recipe = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise core.ClaimError(f"invalid recipe {path}: {exc}") from exc

    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe needs a [claim] table")
    if not isinstance(claim.get("name"), str) or not claim["name"]:
        raise core.ClaimError("claim name must be a nonempty string")
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
    for item in inputs:
        _path(directory, item)
    for key in ("inputs_manifest", "environment"):
        if key in claim:
            _path(directory, claim[key])
    if "inputs_manifest" in claim and version < 2:
        raise core.ClaimError("inputs_manifest requires claim format 2")
    if "inputs_manifest" in claim:
        _read_input_manifest(directory, claim["inputs_manifest"])

    if "requires" in claim and (not isinstance(claim["requires"], list) or
                                any(not isinstance(x, str) or not x for x in claim["requires"])):
        raise core.ClaimError("claim requires must be a list of names")
    for key in ("gate_timeout", "tolerance"):
        if key in claim and not _positive_number(claim[key]):
            raise core.ClaimError(f"claim {key} must be positive")
    if "mutation_floor" in claim:
        floor = claim["mutation_floor"]
        if type(floor) not in (int, float) or not 0 <= floor <= 1:
            raise core.ClaimError("claim mutation_floor must be between zero and one")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope or any(
            unit not in core.COST_UNITS or not _positive_number(value)
            for unit, value in envelope.items()
        ):
            raise core.ClaimError("claim envelope must contain positive known cost ceilings")

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe steps must be an array")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise core.ClaimError(f"step {number} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step {number} has invalid kind: {kind!r}")
        _path(directory, step.get("output"))
        if kind == "gate" and (not isinstance(step.get("run"), str) or not step["run"]):
            raise core.ClaimError(f"gate step {number} needs a run command")
        klass = step.get("class", "generated" if kind == "produce" else "pinned")
        if klass not in ("generated", "pinned", "validated"):
            raise core.ClaimError(f"step {number} has invalid class: {klass!r}")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"step {number} {key} must be a string")
        if "from" in step and (not isinstance(step["from"], str) or not step["from"]):
            raise core.ClaimError(f"step {number} from must be a name")
    return recipe
