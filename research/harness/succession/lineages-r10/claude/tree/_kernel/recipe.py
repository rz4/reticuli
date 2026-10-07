"""The recipe: parsing a claim's untrusted `reticuli.toml` (or `claim.toml`).

`load_recipe` reads whichever recipe name is present (preferring
`reticuli.toml`), parses it, and validates the shape every claim must have
(`spec/claim-format.md`): a string `[claim] name`, and every `[[step]]` a
`kind` in {produce, gate} and an `output`, with a gate additionally needing
a `run`. A malformed or hostile recipe refuses in band as a `ClaimError`,
never a raw parse traceback -- the claim's own recipe is untrusted input.

Stdlib only.
"""
import os
import tomllib

from .core import RECIPE, LEGACY_RECIPE, KINDS, ClaimError, _safe


def recipe_path(d: str) -> str:
    """The recipe file under claim directory `d`: `reticuli.toml` preferred,
    `claim.toml` read under its legacy name."""
    primary = os.path.join(d, RECIPE)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(d, LEGACY_RECIPE)
    if os.path.isfile(legacy):
        return legacy
    raise ClaimError(f"no recipe found: neither {RECIPE!r} nor {LEGACY_RECIPE!r} in {d!r}")


def _validate(parsed) -> None:
    if not isinstance(parsed, dict):
        raise ClaimError("a recipe must be a TOML table")
    claim = parsed.get("claim")
    if not isinstance(claim, dict):
        raise ClaimError("a recipe needs a [claim] table")
    name = claim.get("name")
    if not isinstance(name, str):
        raise ClaimError("[claim] name is required and must be a string")
    steps = parsed.get("step", [])
    if not isinstance(steps, list):
        raise ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise ClaimError("every step must be a table")
        kind = step.get("kind")
        if kind not in KINDS:
            raise ClaimError(f"a step kind must be one of {sorted(KINDS)}, got {kind!r}")
        if not isinstance(step.get("output"), str) or not step["output"]:
            raise ClaimError("every step needs a string output")
        if kind == "gate" and not isinstance(step.get("run"), str):
            raise ClaimError("a gate step needs a string run command")


def load_recipe(d: str) -> dict:
    """Parse and validate the recipe at claim directory `d`.

    Refuses, as a `ClaimError`, anything that is not valid TOML and anything
    that does not meet the validation rules of `spec/claim-format.md`.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    _validate(parsed)
    return parsed


def _steps(parsed: dict) -> list:
    """Every step, in the order the recipe's authoring tool wrote them."""
    return list(parsed.get("step", []))


def gates(parsed: dict) -> list:
    """The gate steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "gate"]


def produces(parsed: dict) -> list:
    """The produce steps, in recipe order."""
    return [s for s in _steps(parsed) if s.get("kind") == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The outputs of every produce step whose class is `generated`
    (the default for a produce step when `class` is omitted)."""
    return [s["output"] for s in produces(parsed)
            if s.get("class", "generated") == "generated"]


def _read_input_manifest(path: str) -> list:
    """Parse an `inputs_manifest` file: one entry per line, optionally
    `<sha256>  <path>`, blank lines and `#` comments ignored."""
    paths = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            paths.append(parts[-1] if len(parts) > 1 else parts[0])
    return paths


def _inputs(parsed: dict, d: str) -> list:
    """The claim's pinned input paths: the `[claim] inputs` list, or the
    contents of `[claim] inputs_manifest` when that is declared instead."""
    claim = parsed.get("claim", {})
    manifest = claim.get("inputs_manifest")
    if manifest is not None:
        path = _safe(d, manifest)
        return _read_input_manifest(path)
    inputs = claim.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ClaimError("[claim] inputs must be a list of strings")
    return list(inputs)
