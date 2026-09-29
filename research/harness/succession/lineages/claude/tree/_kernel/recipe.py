"""reticuli._kernel.recipe -- parsing a claim's recipe.

A claim directory holds its recipe under `reticuli.toml` (or, for older
claims, `claim.toml`). The recipe names the claim and lists its steps in
order: `produce` steps that generate bytes, `gate` steps that validate
them, and (at higher layers) `sign` / `vendor` steps.

`load_recipe` is the only way in: it finds the recipe file, parses it,
and refuses -- always as a `core.ClaimError`, never a raw traceback --
any recipe that is not well-formed TOML or names a step of an unknown
kind. Everything else here reads the parsed result.
"""
import os
import tomllib

from . import core


def recipe_path(room: str) -> str:
    """The path to `room`'s recipe file, preferring `reticuli.toml`."""
    for name in (core.RECIPE, core.LEGACY_RECIPE):
        path = core._safe(room, name)
        if os.path.isfile(path):
            return path
    raise core.ClaimError(f"no recipe found in {room!r}")


def load_recipe(room: str) -> dict:
    """Parse `room`'s recipe and return it, validated, as a dict."""
    path = recipe_path(room)
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise core.ClaimError(f"malformed recipe {path!r}: {exc}") from exc
    except OSError as exc:
        raise core.ClaimError(f"unreadable recipe {path!r}: {exc}") from exc

    if not isinstance(parsed.get("claim"), dict):
        raise core.ClaimError(f"recipe {path!r} is missing a [claim] table")

    for step in parsed.get("step", []):
        if not isinstance(step, dict):
            raise core.ClaimError(f"recipe {path!r} has a malformed step")
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"recipe {path!r} names an unknown step kind: {kind!r}")
        if "output" not in step:
            raise core.ClaimError(f"recipe {path!r} has a step with no output")

    return parsed


def _steps(parsed: dict) -> list:
    """All steps, in the order they appear in the recipe."""
    return parsed.get("step", [])


def gates(parsed: dict) -> list:
    """The `gate` steps, in order."""
    return [s for s in _steps(parsed) if s["kind"] == "gate"]


def produces(parsed: dict) -> list:
    """The `produce` steps, in order."""
    return [s for s in _steps(parsed) if s["kind"] == "produce"]


def generated_outputs(parsed: dict) -> list:
    """The output names of every generated (model-written) produce step."""
    return [p["output"] for p in produces(parsed) if p.get("class") == "generated"]


def _inputs(parsed: dict) -> list:
    """The claim's declared input file names."""
    return parsed.get("claim", {}).get("inputs", [])


def _read_input_manifest(room: str, parsed: dict) -> dict:
    """Map each declared input name to the sha256 of its bytes in `room`."""
    manifest = {}
    for name in _inputs(parsed):
        path = core._safe(room, name)
        try:
            manifest[name] = core._hash_file(path)
        except OSError as exc:
            raise core.ClaimError(f"missing declared input {name!r}: {exc}") from exc
    return manifest
