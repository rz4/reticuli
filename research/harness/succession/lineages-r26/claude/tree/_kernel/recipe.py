"""Parsing a claim's recipe -- untrusted bytes in, a validated structure out.

`load_recipe` reads `reticuli.toml` (preferring it over the legacy
`claim.toml`), parses it as TOML, and validates it against the rules of
`spec/claim-format.md`: `[claim] name` is a required string, every step has
a `kind` in {produce, gate} and an `output`, a gate additionally needs a
`run`, and every path the recipe declares is confined to the claim
directory. A malformed or hostile recipe refuses in band, as a
`ClaimError`, never a raw parser traceback.

Stdlib only.
"""
import tomllib

from . import core
from .core import ClaimError

# -- finding the recipe -------------------------------------------------------


def recipe_path(d: str) -> str:
    """The recipe file under claim directory `d`, preferring its v2 name."""
    primary = f"{d}/{core.RECIPE}"
    import os
    if os.path.isfile(primary):
        return primary
    legacy = f"{d}/{core.LEGACY_RECIPE}"
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(
        f"no recipe found in {d!r}: expected {core.RECIPE} or {core.LEGACY_RECIPE}"
    )


# -- loading and validating ---------------------------------------------------


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at `d`; refusals, never crashes."""
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ClaimError(f"malformed recipe {path!r}: {e}") from e
    except OSError as e:
        raise ClaimError(f"cannot read recipe {path!r}: {e}") from e
    _validate(d, parsed)
    return parsed


def _validate(d: str, parsed: dict) -> None:
    if not isinstance(parsed, dict):
        raise ClaimError("a recipe must be a table")

    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")

    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")

    fmt = claim.get("format", 1)
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt < 1:
        raise ClaimError("[claim] format must be a positive integer")
    if fmt > core.FORMAT:
        raise ClaimError(
            f"claim format {fmt} is newer than this kernel understands "
            f"(format {core.FORMAT}); upgrade reticuli to read it"
        )

    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    for p in inputs:
        core._safe(d, p)

    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        if not isinstance(manifest, str):
            raise ClaimError("[claim] inputs_manifest must be a string")
        core._safe(d, manifest)

    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("the [[step]] array must be a list")
    for step in steps:
        _validate_step(d, step)


def _validate_step(d: str, step) -> None:
    if not isinstance(step, dict):
        raise ClaimError("a step must be a table")
    kind = step.get("kind")
    if kind not in core.KINDS:
        raise ClaimError(f"unknown step kind: {kind!r}")
    output = step.get("output")
    if not isinstance(output, str) or not output:
        raise ClaimError("a step needs a string output")
    core._safe(d, output)
    if kind == "gate":
        run = step.get("run")
        if not isinstance(run, str) or not run:
            raise ClaimError("a gate step needs a run command")


# -- reading the parsed structure ---------------------------------------------


def _steps(parsed: dict) -> list:
    """Every step, in the order the recipe declares them."""
    return list(parsed.get("step", []))


def _default_class(step: dict) -> str:
    return "generated" if step.get("kind") == "produce" else "pinned"


def gates(parsed: dict) -> list:
    """The gate steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The outputs whose step class is `generated` -- outside the root."""
    return [
        s["output"]
        for s in _steps(parsed)
        if s.get("class", _default_class(s)) == "generated"
    ]


def _inputs(parsed: dict) -> list:
    """The pinned input paths the recipe declares explicitly."""
    return list(parsed.get("claim", {}).get("inputs", []))


def _read_input_manifest(path: str) -> list:
    """Paths listed in an `inputs_manifest` file.

    One entry per line, optionally `<sha256>  <path>`; blank lines and
    `#` comments are ignored.
    """
    paths = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            paths.append(parts[1] if len(parts) == 2 and len(parts[0]) == 64 else parts[0])
    return paths
