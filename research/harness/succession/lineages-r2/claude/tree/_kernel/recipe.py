"""Recipe: parsing and validating a claim's untrusted reticuli.toml.

`load_recipe` finds the recipe under either name (`reticuli.toml`,
preferred, or the legacy `claim.toml`), parses it as TOML, and validates
its shape. A malformed or hostile recipe refuses in band with a
`core.ClaimError` -- never a raw parser traceback, because the claim's own
recipe is untrusted input (spec/claim-format.md).

The parsed document keeps the TOML shape (`{"claim": {...}, "step": [...]}`)
so callers can read declared fields directly; steps are normalized in
place (kind checked, output path confined to the claim directory, class
defaulted per spec). The directory a recipe was loaded from is kept under
the private key `_dir`, so downstream readers (`_inputs`, `gates`,
`produces`, `generated_outputs`) need only the parsed document.
"""
import os

import tomllib

from . import core
from .core import ClaimError

_DIR_KEY = "_dir"


def recipe_path(d: str) -> str:
    """The recipe file under `d`: `reticuli.toml`, else legacy `claim.toml`."""
    primary = os.path.join(d, core.RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe ({core.RECIPE} or {core.LEGACY_RECIPE}) in {d!r}")


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one path per line, `<sha256>  <path>`
    optional, blank lines and `#` comments ignored (spec/claim-format.md)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read inputs manifest {path!r}: {e}") from e
    except UnicodeDecodeError as e:
        raise ClaimError(f"inputs manifest {path!r} is not valid UTF-8: {e}") from e

    paths = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        entry = parts[1].strip() if len(parts) == 2 and len(parts[0]) == 64 else line
        paths.append(entry)
    return paths


def _step_class(step: dict) -> str:
    """The step's declared class, or the spec default for its kind."""
    declared = step.get("class")
    if declared is not None:
        return declared
    return "generated" if step.get("kind") == "produce" else "pinned"


def _validate_path(d: str, name, what: str) -> str:
    if not isinstance(name, str):
        raise ClaimError(f"{what} must be a string: {name!r}")
    core._safe(d, name)
    return name


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe under claim directory `d`.

    Refuses in band (`core.ClaimError`) on malformed TOML, a missing or
    non-string `[claim] name`, a `format` newer than this kernel
    understands, a step with an unknown `kind` or a missing required
    field, or any path that escapes the claim directory.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e

    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise ClaimError(f"recipe {path!r} is not valid UTF-8: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e

    if not isinstance(doc, dict) or not isinstance(doc.get("claim"), dict):
        raise ClaimError(f"recipe {path!r} has no [claim] table")

    claim = doc["claim"]
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ClaimError(f"[claim] format must be a positive integer: {fmt!r}")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list):
        raise ClaimError("[claim] inputs must be a list of paths")
    for p in inputs:
        _validate_path(d, p, "an [claim] inputs path")

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        _validate_path(d, manifest, "[claim] inputs_manifest")

    steps = doc.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")

    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError(f"a step must be a table: {step!r}")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise ClaimError(f"a step kind must be one of {sorted(core.KINDS)}: {kind!r}")
        output = step.get("output")
        _validate_path(d, output, "a step output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError(f"a gate step needs a string run: {step!r}")
        step["class"] = _step_class(step)

    doc[_DIR_KEY] = os.path.realpath(d)
    return doc


def _steps(parsed: dict) -> list:
    """Every step, in recipe order."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The `gate` steps, in recipe order."""
    return [s for s in _steps(parsed) if s["kind"] == "gate"]


def produces(parsed: dict) -> list:
    """The `produce` steps, in recipe order."""
    return [s for s in _steps(parsed) if s["kind"] == "produce"]


def generated_outputs(parsed: dict) -> list:
    """Outputs whose step class is `generated` (v1: `free`) -- outside the root."""
    return [s["output"] for s in _steps(parsed) if s["class"] in ("generated", "free")]


def _inputs(parsed: dict) -> list:
    """Every pinned input path: `[claim] inputs`, plus an `inputs_manifest`
    (itself a pinned input) and the paths it names, in that order."""
    claim = parsed["claim"]
    paths = list(claim.get("inputs", []))
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        paths.append(manifest)
        paths.extend(_read_input_manifest(os.path.join(parsed[_DIR_KEY], manifest)))
    return paths
