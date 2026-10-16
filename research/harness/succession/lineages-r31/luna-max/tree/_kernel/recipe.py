"""Safe parsing and small queries for a Reticuli claim recipe.

Recipes are untrusted TOML.  Keep parse, validation, and filesystem failures
inside the kernel's :class:`ClaimError` boundary.
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import os
import re
import tomllib
from typing import Any

from . import core


_HASH_LINE = re.compile(r"^([0-9a-f]{64}) {2,}(.+)$")
_HASH_PREFIX = re.compile(r"^[0-9a-fA-F]{64}\\s")
_CLASSES = frozenset({"generated", "pinned", "validated", "free", "exact"})


def recipe_path(directory: os.PathLike | str) -> str:
    """Return the path of the recipe in *directory*.

    The current filename wins when both are present.  The former
    ``claim.toml`` name remains readable for already-sealed claims.
    """
    try:
        for filename in (core.RECIPE, core.LEGACY_RECIPE):
            candidate = core._safe(directory, filename)
            try:
                os.lstat(candidate)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise core.ClaimError(
                    f"cannot inspect recipe {candidate!r}: {exc}"
                ) from exc
            return candidate
    except core.ClaimError:
        raise
    except Exception as exc:
        raise core.ClaimError(f"cannot locate claim recipe: {exc}") from exc
    raise core.ClaimError(
        f"claim has neither {core.RECIPE!r} nor {core.LEGACY_RECIPE!r}"
    )


def _claim_table(recipe: Any) -> dict[str, Any]:
    """Get the claim table, accepting the v1 table spelling as well."""
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    claim = recipe.get("claim")
    legacy = recipe.get("record")
    if claim is not None and legacy is not None:
        raise core.ClaimError("recipe cannot contain both [claim] and [record]")
    if claim is None:
        claim = legacy
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe must contain a [claim] table")
    return claim


def _steps(recipe: Any) -> list[dict[str, Any]]:
    """Return the recipe's steps in their authored order."""
    if not isinstance(recipe, dict):
        raise core.ClaimError("recipe must be a TOML table")
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe 'step' must be an array of tables")
    if any(not isinstance(step, dict) for step in steps):
        raise core.ClaimError("every recipe step must be a table")
    return steps


def gates(recipe: Any) -> list[dict[str, Any]]:
    """Return gate steps without changing their authored order."""
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe: Any) -> list[dict[str, Any]]:
    """Return produce steps without changing their authored order."""
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe: Any) -> list[str]:
    """Return generated produce-step output names.

    The historical ``free`` class is equivalent to ``generated``.  A produce
    step with no explicit class has always meant a generated output.
    """
    result: list[str] = []
    for step in produces(recipe):
        step_class = step.get("class", "generated")
        if step_class in ("generated", "free"):
            output = step.get("output")
            if isinstance(output, str):
                result.append(output)
    return result


def _path_in_claim(directory: os.PathLike | str, name: Any, what: str) -> str:
    if not isinstance(name, str):
        raise core.ClaimError(f"{what} must be a string path")
    try:
        return core._safe(directory, name)
    except core.ClaimError as exc:
        raise core.ClaimError(f"invalid {what} {name!r}: {exc}") from exc


def _read_input_manifest(root_or_path: Any, name: Any = None) -> list[str]:
    """Read an ``inputs_manifest`` and return its claim-relative paths.

    Normally pass ``(claim_directory, manifest_name)``.  Passing the
    manifest's path alone is also supported.  Manifest rows may be plain
    paths or ``<sha256>  <path>``; supplied digests are checked against the
    named regular files.
    """
    if isinstance(root_or_path, dict):
        # A convenient form for callers already holding a parsed recipe:
        # _read_input_manifest(recipe, claim_directory).
        recipe = root_or_path
        if name is None:
            raise core.ClaimError("claim directory is required for input manifest")
        root = name
        claim = _claim_table(recipe)
        manifest_name = claim.get("inputs_manifest")
    elif name is None:
        manifest_path = core._as_path(root_or_path)
        if not manifest_path:
            raise core.ClaimError("input manifest path must not be empty")
        manifest_path = os.path.abspath(manifest_path)
        root = os.path.dirname(manifest_path)
        manifest_name = os.path.basename(manifest_path)
    else:
        root = root_or_path
        manifest_name = name

    manifest_path = _path_in_claim(root, manifest_name, "input manifest")
    # Hashing also enforces the ordinary-file, single-hard-link rule and
    # refuses a missing manifest before any parsing is attempted.
    core._hash_file(manifest_path)
    try:
        with open(manifest_path, "rb") as stream:
            raw = stream.read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(
            f"cannot read input manifest {manifest_name!r}: {exc}"
        ) from exc

    paths: list[str] = []
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue

        expected: str | None = None
        match = _HASH_LINE.fullmatch(line)
        if match:
            expected, path = match.groups()
        else:
            if _HASH_PREFIX.match(line):
                raise core.ClaimError(
                    f"malformed hash entry on line {number} of input manifest "
                    f"{manifest_name!r}"
                )
            path = line

        safe_path = _path_in_claim(root, path, "manifest input")
        # A manifest is a fixed list, not a pattern or a promise about files
        # that may appear later.  Check every named file now, even when the
        # row did not include an expected digest.
        actual = core._hash_file(safe_path)
        if expected is not None and actual != expected:
            raise core.ClaimError(
                f"input manifest digest mismatch for {path!r}: "
                f"expected {expected}, got {actual}"
            )
        paths.append(path)
    return paths


def _inputs(recipe: Any, directory: os.PathLike | str | None = None) -> list[str]:
    """List all pinned input names declared by a recipe.

    Direct inputs retain their order, followed by manifest-declared inputs;
    the manifest itself and the optional environment file are pinned too.
    """
    claim = _claim_table(recipe)
    result: list[str] = []

    declared = claim.get("inputs", [])
    if not isinstance(declared, list):
        raise core.ClaimError("claim 'inputs' must be an array of paths")
    for path in declared:
        if not isinstance(path, str):
            raise core.ClaimError("every claim input must be a string path")
        if directory is not None:
            _path_in_claim(directory, path, "claim input")
        result.append(path)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise core.ClaimError("claim 'inputs_manifest' must be a string path")
        if directory is None:
            raise core.ClaimError(
                "claim directory is required to read 'inputs_manifest'"
            )
        _path_in_claim(directory, manifest, "input manifest")
        result.append(manifest)
        result.extend(_read_input_manifest(directory, manifest))

    environment = claim.get("environment")
    if environment is not None:
        if not isinstance(environment, str):
            raise core.ClaimError("claim 'environment' must be a string path")
        if directory is not None:
            _path_in_claim(directory, environment, "environment file")
        result.append(environment)
    return result


def _reject_dates(value: Any, where: str = "recipe") -> None:
    """Reject TOML date/time values, which have no identity JSON form."""
    if isinstance(value, (_datetime.datetime, _datetime.date, _datetime.time)):
        raise core.ClaimError(f"TOML date/time value is not supported in {where}")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_dates(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_dates(child, f"{where}[{index}]")


def _validate_recipe(recipe: Any, directory: os.PathLike | str) -> None:
    _reject_dates(recipe)
    claim = _claim_table(recipe)

    if not isinstance(claim.get("name"), str):
        raise core.ClaimError("claim 'name' is required and must be a string")

    if "format" in claim:
        version = claim["format"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise core.ClaimError("claim 'format' must be a positive integer")
        understood = getattr(core, "FORMAT", 1)
        if version > understood:
            raise core.ClaimError(
                f"claim format {version} is newer than this kernel understands "
                f"(format {understood}); upgrade reticuli to read it"
            )

    declared = claim.get("inputs", [])
    if not isinstance(declared, list):
        raise core.ClaimError("claim 'inputs' must be an array of paths")
    for path in declared:
        _path_in_claim(directory, path, "claim input")

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise core.ClaimError("claim 'inputs_manifest' must be a string path")
        if claim.get("format", 1) < 2:
            raise core.ClaimError("'inputs_manifest' requires claim format 2 or newer")
        _path_in_claim(directory, manifest, "input manifest")
        # Validate and read the fixed list now so malformed/missing entries
        # are refusals rather than later filesystem tracebacks.
        _read_input_manifest(directory, manifest)

    environment = claim.get("environment")
    if environment is not None:
        _path_in_claim(directory, environment, "environment file")

    requires = claim.get("requires", [])
    if not isinstance(requires, list) or any(not isinstance(item, str) for item in requires):
        raise core.ClaimError("claim 'requires' must be an array of strings")

    for index, step in enumerate(_steps(recipe)):
        kind = step.get("kind")
        if kind not in ("produce", "gate"):
            raise core.ClaimError(
                f"step {index + 1} has invalid kind {kind!r}; expected 'produce' or 'gate'"
            )
        if "output" not in step:
            raise core.ClaimError(f"step {index + 1} is missing 'output'")
        _path_in_claim(directory, step["output"], f"step {index + 1} output")

        if kind == "gate":
            if "run" not in step or not isinstance(step["run"], str):
                raise core.ClaimError(
                    f"gate step {index + 1} needs a string 'run' command"
                )

        if "class" in step and step["class"] not in _CLASSES:
            raise core.ClaimError(
                f"step {index + 1} has invalid class {step['class']!r}"
            )
        for hint in ("guidance", "request"):
            if hint in step and not isinstance(step[hint], str):
                raise core.ClaimError(
                    f"step {index + 1} {hint!r} must be a string"
                )


def load_recipe(directory: os.PathLike | str) -> dict[str, Any]:
    """Read, parse, and validate a claim recipe, refusing malformed input."""
    path = recipe_path(directory)
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
        text = raw.decode("utf-8")
        parsed = tomllib.loads(text)
        _validate_recipe(parsed, directory)
        return parsed
    except core.ClaimError:
        raise
    except Exception as exc:
        # Includes TOMLDecodeError, invalid UTF-8, and filesystem/parser
        # corner cases.  Recipe bytes are untrusted, so none escape as a raw
        # implementation traceback.
        raise core.ClaimError(f"cannot load recipe {path!r}: {exc}") from exc
