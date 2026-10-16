"""Parsing and small queries for a claim recipe.

Recipe files are claim-controlled input.  This module consequently turns parse,
I/O, and schema failures into :class:`ClaimError` rather than allowing a TOML
or filesystem exception to cross the kernel boundary.
"""

from __future__ import annotations

import datetime as _datetime
import math
import os
import re
import stat
from typing import Any

import tomllib

from . import core


_MANIFEST_DIGEST = re.compile(r"^([0-9a-f]{64})[ \t]{2,}(.+)$")
_STEP_CLASSES = frozenset({"generated", "pinned", "validated", "free", "exact"})


def recipe_path(d: str | os.PathLike[str]) -> str:
    """Return the recipe in *d*, preferring the canonical filename.

    The recipe itself may not be a symlink, directory, device, or multiply
    linked file.  Those checks keep reading the recipe subject to the same
    anti-aliasing rules as other identity-bearing claim files.
    """

    directory = os.fspath(d)
    try:
        for name in (core.RECIPE, core.LEGACY_RECIPE):
            path = core._safe(directory, name)
            if not os.path.lexists(path):
                continue
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                raise core.ClaimError(f"recipe is not a regular file: {name}")
            if info.st_nlink != 1:
                raise core.ClaimError(f"recipe has multiple hard links: {name}")
            return path
    except core.ClaimError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot inspect claim recipe: {exc}") from None
    raise core.ClaimError(
        f"claim has no {core.RECIPE} or {core.LEGACY_RECIPE}"
    )


def _steps(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the recipe steps in their authored order."""

    steps = recipe.get("step", [])
    return steps if isinstance(steps, list) else []


def gates(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all gate steps, preserving recipe order."""

    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all produce steps, preserving recipe order."""

    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: dict[str, Any]) -> list[str]:
    """Return outputs whose concrete bytes belong to this realization.

    A produce step defaults to ``generated``.  Outputs supplied through a
    component (a step carrying ``from``) are deliberately excluded: their
    bytes belong to that component's realization rather than this claim's
    build digest.
    """

    result: list[str] = []
    for step in produces(recipe):
        step_class = step.get("class", "generated")
        if step_class in ("generated", "free") and "from" not in step:
            result.append(step["output"])
    return result


def _read_input_manifest(
    d: str | os.PathLike[str], name: str | None = None
) -> list[str]:
    """Read an ``inputs_manifest`` and return its declared paths.

    ``d, name`` denotes a claim-relative manifest.  Supplying only ``d`` is
    also accepted as a convenience for callers that already resolved the
    manifest path.  Lines are either a path or ``<sha256>  <path>``; blank
    lines and comment lines are ignored.
    """

    display = os.fspath(d) if name is None else name
    try:
        path = os.fspath(d) if name is None else core._safe(d, name)
        with open(path, "r", encoding="utf-8", newline=None) as stream:
            lines = stream.readlines()
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(
            f"cannot read input manifest {display!r}: {exc}"
        ) from None

    entries: list[str] = []
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matched = _MANIFEST_DIGEST.fullmatch(line)
        entry = matched.group(2) if matched else line
        entry = entry.strip()
        if not entry:
            raise core.ClaimError(
                f"input manifest {display!r} has an empty path on line {number}"
            )
        entries.append(entry)
    return entries


def _inputs(
    recipe: dict[str, Any], d: str | os.PathLike[str] | None = None
) -> list[str]:
    """Return all pinned input names declared by *recipe*.

    Manifest entries are expanded when *d* is supplied; the manifest itself
    is pinned too.  A declared environment file is likewise automatically an
    input.  Duplicate declarations collapse to their first occurrence.
    """

    claim = recipe.get("claim", {})
    names = list(claim.get("inputs", []))

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if d is None:
            raise core.ClaimError("a claim directory is needed to read inputs_manifest")
        names.extend(_read_input_manifest(d, manifest))
        names.append(manifest)

    environment = claim.get("environment")
    if environment is not None:
        names.append(environment)

    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _number(value: Any, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return value > 0 if positive else value >= 0


def _validate_json_values(value: Any, where: str = "recipe") -> None:
    """Refuse TOML values for which the identity JSON has no portable form."""

    if isinstance(value, (_datetime.date, _datetime.time)):
        raise core.ClaimError(f"{where} contains a TOML date or time")
    if isinstance(value, float) and not math.isfinite(value):
        raise core.ClaimError(f"{where} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_json_values(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_values(child, f"{where}[{index}]")


def _validate_path(d: str | os.PathLike[str], value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise core.ClaimError(f"{what} must be a non-empty path string")
    try:
        core._safe(d, value)
    except core.ClaimError as exc:
        raise core.ClaimError(f"invalid {what}: {exc}") from None
    return value


def _validate_recipe(recipe: Any, d: str | os.PathLike[str]) -> dict[str, Any]:
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    _validate_json_values(recipe)

    claim = recipe.get("claim")
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe requires a [claim] table")
    if not isinstance(claim.get("name"), str):
        raise core.ClaimError("[claim] name is required and must be a string")

    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise core.ClaimError("[claim] format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise core.ClaimError("[claim] inputs must be an array of paths")
    for item in inputs:
        _validate_path(d, item, "input")

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        _validate_path(d, manifest, "inputs_manifest")
        if version < 2:
            raise core.ClaimError("inputs_manifest requires claim format 2 or newer")

    environment = claim.get("environment")
    if environment is not None:
        _validate_path(d, environment, "environment")

    requires = claim.get("requires")
    if requires is not None and (
        not isinstance(requires, list)
        or any(not isinstance(item, str) or not item for item in requires)
    ):
        raise core.ClaimError("[claim] requires must be an array of strings")

    timeout = claim.get("gate_timeout")
    if timeout is not None and not _number(timeout, positive=True):
        raise core.ClaimError("[claim] gate_timeout must be a positive number")

    tolerance = claim.get("tolerance")
    if tolerance is not None and (
        not _number(tolerance) or not (1.5 <= tolerance < 4.0)
    ):
        raise core.ClaimError("[claim] tolerance must be in [1.5, 4.0)")

    floor = claim.get("mutation_floor")
    if floor is not None and (
        not _number(floor) or not (0 <= floor <= 1)
    ):
        raise core.ClaimError("[claim] mutation_floor must be between 0 and 1")

    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("[claim] envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise core.ClaimError(f"unknown envelope unit: {unit!r}")
            if not _number(ceiling, positive=True):
                raise core.ClaimError(
                    f"envelope ceiling for {unit!r} must be a positive number"
                )

    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("[[step]] entries must form an array")
    for index, step in enumerate(steps):
        label = f"step {index + 1}"
        if not isinstance(step, dict):
            raise core.ClaimError(f"{label} must be a table")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"{label} has unknown kind {kind!r}")
        _validate_path(d, step.get("output"), f"{label} output")
        step_class = step.get("class")
        if step_class is not None and step_class not in _STEP_CLASSES:
            raise core.ClaimError(f"{label} has unknown class {step_class!r}")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise core.ClaimError(f"{label} gate requires a string run command")
        for key in core.GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"{label} {key} must be a string")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError(f"{label} from must be a string")

    # Reading a manifest is part of parsing it: malformed entries and missing
    # manifest files are recipe refusals, while ordinary input existence is
    # checked by identity computation when those bytes are hashed.
    if manifest is not None:
        for entry in _read_input_manifest(d, manifest):
            _validate_path(d, entry, "manifest input")

    return recipe


def load_recipe(d: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse and validate the recipe in claim directory *d*.

    All failures caused by claim-controlled bytes or paths are reported as
    :class:`core.ClaimError`.
    """

    try:
        path = recipe_path(d)
        with open(path, "rb") as stream:
            parsed = tomllib.load(stream)
        return _validate_recipe(parsed, d)
    except core.ClaimError:
        raise
    except (tomllib.TOMLDecodeError, OSError, UnicodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot load claim recipe: {exc}") from None
