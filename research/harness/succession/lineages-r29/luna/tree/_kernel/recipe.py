"""Parsing and validation of an untrusted Reticuli recipe.

The recipe is deliberately kept as the TOML parser returned it: identity is
computed from parsed content, and in particular defaults are interpreted by
helpers rather than written back into the document.
"""

import math
import os
import re
import stat
import tomllib

from . import core


_RECIPE_NAMES = (core.RECIPE, core.LEGACY_RECIPE)
_STEP_KINDS = frozenset(("produce", "gate"))
_STEP_CLASSES = frozenset(("generated", "pinned", "validated", "free", "exact"))
_GUIDANCE_KEYS = ("guidance", "request")
_COST_UNITS = frozenset(("usd", "tokens", "calls", "seconds"))
_HEX256 = re.compile(r"^[0-9a-fA-F]{64}$")


def recipe_path(directory):
    """Return the selected recipe file, preferring ``reticuli.toml``.

    ``claim.toml`` remains a supported legacy name.  The filename itself is
    not part of claim identity.
    """
    directory = os.fspath(directory)
    for name in _RECIPE_NAMES:
        candidate = os.path.join(directory, name)
        try:
            info = os.lstat(candidate)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise core.ClaimError(f"cannot inspect recipe {candidate!r}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise core.ClaimError(f"refusing symlink recipe: {candidate!r}")
        if not stat.S_ISREG(info.st_mode):
            raise core.ClaimError(f"recipe is not a regular file: {candidate!r}")
        if info.st_nlink != 1:
            raise core.ClaimError(f"refusing recipe with multiple hard links: {candidate!r}")
        return candidate
    raise core.ClaimError(
        f"claim has no {core.RECIPE!r} or legacy {core.LEGACY_RECIPE!r} recipe"
    )


def _path_name(name, root=None):
    """Validate a claim-relative path and, when possible, inspect its entries."""
    if not isinstance(name, str) or not name:
        raise core.ClaimError("claim path must be a non-empty relative path")
    # TOML paths use slash spelling. Accept backslashes as separators, like
    # core._safe, but do not let a Windows drive path become relative on Unix.
    normalized = name.replace("\\", "/")
    drive, _ = os.path.splitdrive(name)
    if (os.path.isabs(name) or normalized.startswith("/") or drive
            or (len(normalized) >= 2 and normalized[1] == ":")):
        raise core.ClaimError(f"absolute claim path is not allowed: {name!r}")
    components = normalized.split("/")
    if any(part in ("", ".", "..") for part in components):
        raise core.ClaimError(f"unsafe claim path: {name!r}")
    if root is None:
        return normalized

    # core._safe rejects every symlink component and verifies confinement.
    resolved = core._safe(root, normalized)
    # Filesystems such as the default macOS volume can resolve a differently
    # cased name. Identity must not depend on that host behavior, so whenever
    # a component exists require an exact directory-entry spelling.
    current = os.path.realpath(os.fspath(root))
    for component in components:
        try:
            entries = os.listdir(current)
        except OSError:
            break  # missing parent; existence is checked by the operation using it
        if component not in entries:
            alternate = next((entry for entry in entries
                              if entry.casefold() == component.casefold()), None)
            if alternate is not None:
                raise core.ClaimError(
                    f"claim path component has incorrect case: {name!r}"
                )
            # The remainder cannot be inspected until this path is materialized.
            break
        current = os.path.join(current, component)
    return resolved


def _finite_number(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise core.ClaimError(f"{label} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise core.ClaimError(f"{label} must be finite")
    if positive and value <= 0:
        raise core.ClaimError(f"{label} must be positive")
    if nonnegative and value < 0:
        raise core.ClaimError(f"{label} must be non-negative")


def _json_compatible(value, where="recipe"):
    """Refuse TOML values JSON cannot represent (notably date/time values)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise core.ClaimError(f"{where} contains a non-string key")
            _json_compatible(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _json_compatible(item, f"{where}[{index}]")
    elif isinstance(value, (str, bool, int)) or value is None:
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise core.ClaimError(f"{where} contains a non-finite number")
    else:
        # tomllib returns datetime/date/time objects for TOML date-time values.
        raise core.ClaimError(f"{where} contains a value that cannot be represented in JSON")


def _validate_claim(claim, root):
    if not isinstance(claim, dict):
        raise core.ClaimError("recipe must contain a [claim] table")
    if "name" not in claim or not isinstance(claim["name"], str):
        raise core.ClaimError("[claim].name is required and must be a string")

    version = claim.get("format", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise core.ClaimError("[claim].format must be a positive integer")
    if version > core.FORMAT:
        raise core.ClaimError(
            f"claim format {version} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or any(not isinstance(item, str) for item in inputs):
        raise core.ClaimError("[claim].inputs must be an array of paths")
    for item in inputs:
        _path_name(item, root)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        _path_name(manifest, root)
        if inputs:
            raise core.ClaimError("declare either inputs or inputs_manifest, not both")
        # A manifest is a pinned input and a fixed list. Reading it here makes
        # a missing or malformed manifest a refusal instead of a later crash.
        _read_input_manifest(root, manifest)

    environment = claim.get("environment")
    if environment is not None:
        _path_name(environment, root)
        if not isinstance(environment, str):
            raise core.ClaimError("[claim].environment must be a path string")

    requires = claim.get("requires", [])
    if not isinstance(requires, list) or any(not isinstance(item, str) for item in requires):
        raise core.ClaimError("[claim].requires must be an array of strings")

    if "gate_timeout" in claim:
        _finite_number(claim["gate_timeout"], "[claim].gate_timeout", positive=True)
    if "tolerance" in claim:
        tolerance = claim["tolerance"]
        _finite_number(tolerance, "[claim].tolerance", positive=True)
        if not 1.5 <= tolerance < 4.0:
            raise core.ClaimError("[claim].tolerance must be in [1.5, 4.0)")
    if "mutation_floor" in claim:
        floor = claim["mutation_floor"]
        _finite_number(floor, "[claim].mutation_floor", nonnegative=True)
        if floor > 1:
            raise core.ClaimError("[claim].mutation_floor must be at most 1")

    envelope = claim.get("envelope")
    if envelope is not None:
        if not isinstance(envelope, dict) or not envelope:
            raise core.ClaimError("[claim].envelope must be a non-empty table")
        for unit, ceiling in envelope.items():
            if unit not in _COST_UNITS:
                raise core.ClaimError(f"unknown envelope unit: {unit!r}")
            _finite_number(ceiling, f"[claim].envelope.{unit}", positive=True)


def _validate_steps(recipe, root):
    steps = recipe.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("recipe [[step]] entries must form an array")
    for index, step in enumerate(steps):
        label = f"step {index + 1}"
        if not isinstance(step, dict):
            raise core.ClaimError(f"{label} must be a table")
        kind = step.get("kind")
        if kind not in _STEP_KINDS:
            raise core.ClaimError(f"{label} kind must be 'produce' or 'gate'")
        if "output" not in step:
            raise core.ClaimError(f"{label} is missing output")
        _path_name(step["output"], root)
        if "class" in step and step["class"] not in _STEP_CLASSES:
            raise core.ClaimError(f"{label} has an invalid class")
        if kind == "gate":
            if "run" not in step or not isinstance(step["run"], str) or not step["run"].strip():
                raise core.ClaimError(f"{label} gate requires a non-empty run command")
        for key in _GUIDANCE_KEYS:
            if key in step and not isinstance(step[key], str):
                raise core.ClaimError(f"{label} {key} must be a string")
        if "from" in step and not isinstance(step["from"], str):
            raise core.ClaimError(f"{label} from must be a string")


def load_recipe(directory):
    """Read and validate the recipe in *directory*, returning its TOML object.

    Parse errors, unsafe paths, and schema errors are converted to
    :class:`core.ClaimError`, since a recipe is untrusted input.
    """
    try:
        path = recipe_path(directory)
        with open(path, "rb") as stream:
            data = stream.read()
        parsed = tomllib.loads(data.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise core.ClaimError("recipe must be a TOML table")
        _json_compatible(parsed)
        claim = parsed.get("claim")
        _validate_claim(claim, os.path.abspath(os.fspath(directory)))
        _validate_steps(parsed, os.path.abspath(os.fspath(directory)))
        return parsed
    except core.ClaimError:
        raise
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError, ValueError, TypeError,
            OverflowError, RecursionError) as exc:
        raise core.ClaimError(f"cannot read recipe: {exc}") from exc


def _read_input_manifest(path_or_root, name=None):
    """Read a fixed input manifest and return its paths in authoring order.

    Entries are one path per line, optionally prefixed by a SHA-256 digest
    and two or more spaces.  Supplied digests are checked against the named
    file.  The one-argument form takes the manifest filename; the two-argument
    form takes a claim directory and a claim-relative manifest path.
    """
    if name is None:
        manifest_path = os.fspath(path_or_root)
        manifest_path = os.path.abspath(manifest_path)
        root = os.path.dirname(manifest_path)
        manifest_name = os.path.basename(manifest_path)
    else:
        root = os.path.abspath(os.fspath(path_or_root))
        manifest_name = _path_name(name, root)
        manifest_path = os.path.join(root, manifest_name)

    # Apply the same file rules as all other pinned bytes, and reject links and
    # special files before decoding any data.
    try:
        core._hash_file(manifest_path)
        with open(manifest_path, "rb") as stream:
            text = stream.read().decode("utf-8")
    except core.ClaimError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise core.ClaimError(f"cannot read inputs manifest {manifest_name!r}: {exc}") from exc

    result = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        expected = None
        match = re.match(r"^([0-9a-fA-F]{64})[ \t]{2,}(.*)$", line)
        if match:
            expected, entry = match.group(1).lower(), match.group(2)
        else:
            entry = line
        try:
            relative = _path_name(entry, root)
            if expected is not None:
                actual = core._hash_file(os.path.join(root, relative))
                if actual != expected:
                    raise core.ClaimError(
                        f"inputs manifest digest mismatch for {entry!r}"
                    )
        except core.ClaimError as exc:
            raise core.ClaimError(
                f"invalid inputs manifest line {line_number}: {exc}"
            ) from exc
        result.append(relative)
    return result


def _inputs(recipe, directory=None):
    """Return the ordered pinned-input paths declared by a parsed recipe.

    The manifest file and an environment lock are themselves pinned inputs;
    with *directory* supplied, entries from an inputs manifest are expanded
    into the returned list as well.
    """
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    result = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        result.append(manifest)
        if directory is not None:
            result.extend(_read_input_manifest(directory, manifest))
    environment = claim.get("environment")
    if environment is not None:
        result.append(environment)
    # A path only needs hashing once, while preserving the declaration order.
    return list(dict.fromkeys(result))


def _steps(recipe):
    """Return the recipe's steps in the original authoring order."""
    if not isinstance(recipe, dict):
        return []
    steps = recipe.get("step", [])
    return steps if isinstance(steps, list) else []


def gates(recipe):
    """Return gate steps in recipe order."""
    return [step for step in _steps(recipe) if step.get("kind") == "gate"]


def produces(recipe):
    """Return produce steps in recipe order."""
    return [step for step in _steps(recipe) if step.get("kind") == "produce"]


def generated_outputs(recipe):
    """Return generated output paths, excluding outputs supplied by a layer."""
    outputs = []
    for step in produces(recipe):
        step_class = step.get("class", "generated")
        if step_class in ("generated", "free") and not step.get("from"):
            output = step.get("output")
            if isinstance(output, str):
                outputs.append(output)
    return outputs
