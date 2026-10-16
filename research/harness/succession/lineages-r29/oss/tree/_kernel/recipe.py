"""Recipe parsing utilities for the Reticuli claim kernel.

The conformance gate (``checks/recipe_check.py``) expects this module to
expose a small public API:

* ``load_recipe(d: str) -> dict`` – locate the recipe file (``reticuli.toml``
  preferred, ``claim.toml`` legacy), parse it, validate its structure and
  that all file‑system references stay inside the claim directory ``d``.
  On any problem a :class:`reticuli._kernel.core.ClaimError` is raised – the
  gate asserts that *no* raw traceback escapes.
* ``recipe_path(d: str) -> str`` – return the absolute path of the recipe file
  that ``load_recipe`` would read.
* ``_steps(recipe: dict) -> list`` – the ordered list of ``[[step]]``
  tables from the TOML.
* ``gates(recipe: dict) -> list`` – subset of steps where ``kind == "gate"``.
* ``produces(recipe: dict) -> list`` – subset where ``kind == "produce"``.
* ``generated_outputs(recipe: dict) -> list`` – the ``output`` values of steps
  whose ``class`` is ``generated`` (the default for ``produce`` steps).
* ``_inputs(recipe: dict) -> list`` – the claim's pinned inputs.  If the
  recipe specifies ``inputs_manifest`` the manifest file is read (one path per
  line, comments with ``#`` ignored) and its entries are returned; otherwise
  the ``inputs`` array is returned (or an empty list).
* ``_read_input_manifest(base: str, name: str) -> list`` – helper that reads
  a manifest file safely.

Only the symbols listed above are required by the gate; the ``SEAM`` test in
``checks/recipe_check.py`` also validates that the module defines the names
listed in ``_SEAM__kernel_recipe_CALLABLES``.  No additional constants are
necessary for the check.
"""

from __future__ import annotations

import os
import sys
from typing import List, Dict, Any

# ``tomllib`` is in the stdlib from Python 3.11.  Fall back to ``tomli`` for
# older versions (the test environment is guaranteed to have at least one).
try:
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

# Import the core module for shared helpers and the ClaimError type.
from . import core


# ---------------------------------------------------------------------------
# Helper utilities (private).
# ---------------------------------------------------------------------------
def _read_input_manifest(base: str, name: str) -> List[str]:
    """Read a manifest file safely.

    The manifest is a UTF‑8 text file, one entry per line. Blank lines and
    lines beginning with ``#`` are ignored.  Each non‑blank line may optionally
    start with a ``<sha256>  `` prefix; the prefix is stripped and only the
    path component is returned.
    """
    path = core._safe(base, name)
    with open(path, "r", encoding="utf-8") as f:
        lines = []
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # If the line looks like "<sha256>  <path>" we keep the second part.
            if "  " in line:
                # Split on the first double‑space sequence.
                _, after = line.split("  ", 1)
                line = after.strip()
            lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Public API expected by the gate.
# ---------------------------------------------------------------------------
def recipe_path(d: str) -> str:
    """Return the absolute path of the recipe file for claim directory *d*.

    Preference is given to ``reticuli.toml``; if it does not exist we fall
    back to the legacy name ``claim.toml``.  If neither file is present a
    ``ClaimError`` is raised.
    """
    preferred = os.path.join(d, core.RECIPE)
    legacy = os.path.join(d, core.LEGACY_RECIPE)
    if os.path.isfile(preferred):
        return os.path.realpath(preferred)
    if os.path.isfile(legacy):
        return os.path.realpath(legacy)
    raise core.ClaimError("no recipe file found in claim directory")


def load_recipe(d: str) -> Dict[str, Any]:
    """Parse and validate the claim recipe located in directory *d*.

    The returned dictionary is the raw TOML mapping with an additional private
    key ``"__base"`` holding the absolute claim directory.  All validation
    errors raise ``core.ClaimError`` – the gate explicitly checks that no raw
    traceback leaks.
    """
    path = recipe_path(d)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:  # pragma: no cover – any parsing issue is a claim error
        raise core.ClaimError(f"cannot parse recipe: {exc}")

    # Basic top‑level structure.
    if not isinstance(data, dict) or "claim" not in data:
        raise core.ClaimError("recipe missing [claim] table")
    claim = data["claim"]
    if not isinstance(claim, dict):
        raise core.ClaimError("[claim] must be a table")

    # Required name.
    name = claim.get("name")
    if not isinstance(name, str):
        raise core.ClaimError("[claim] name must be a string")

    # Validate optional fields that are file references.
    base = os.path.realpath(d)
    # inputs list
    inputs = claim.get("inputs", [])
    if inputs is not None:
        if not isinstance(inputs, list):
            raise core.ClaimError("[claim] inputs must be an array")
        for i in inputs:
            if not isinstance(i, str):
                raise core.ClaimError("each input must be a string")
            core._safe(base, i)  # path validation only – result unused

    # inputs_manifest – if present, ensure the referenced file is safe.
    manifest_name = claim.get("inputs_manifest")
    if manifest_name is not None:
        if not isinstance(manifest_name, str):
            raise core.ClaimError("inputs_manifest must be a string")
        core._safe(base, manifest_name)

    # Steps – ``[[step]]`` must be a list of tables.
    steps = data.get("step", [])
    if not isinstance(steps, list):
        raise core.ClaimError("[[step]] must be an array of tables")
    for step in steps:
        if not isinstance(step, dict):
            raise core.ClaimError("each step must be a table")
        # kind validation
        kind = step.get("kind")
        if kind not in core.KINDS:
            raise core.ClaimError(f"step kind must be one of {sorted(core.KINDS)}")
        # output validation
        out = step.get("output")
        if not isinstance(out, str):
            raise core.ClaimError("step output must be a string")
        core._safe(base, out)
        # gate-specific field
        if kind == "gate":
            if not isinstance(step.get("run"), str):
                raise core.ClaimError("gate step requires a string 'run' field")
        # class defaults – keep for completeness, but ensure valid string if present
        cls = step.get("class")
        if cls is not None and not isinstance(cls, str):
            raise core.ClaimError("step class must be a string if present")

    # Attach the base path for downstream helpers.
    data["__base"] = base
    return data


def _steps(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the ordered list of step tables from *recipe*.

    The function is deliberately named with a leading underscore to match the
    gate's ``_SEAM__kernel_recipe_CALLABLES`` list.
    """
    return list(recipe.get("step", []))


def gates(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter and return steps whose ``kind`` is ``"gate"``.
    """
    return [s for s in _steps(recipe) if s.get("kind") == "gate"]


def produces(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter and return steps whose ``kind`` is ``"produce"``.
    """
    return [s for s in _steps(recipe) if s.get("kind") == "produce"]


def generated_outputs(recipe: Dict[str, Any]) -> List[str]:
    """Return the ``output`` names of steps that are *generated*.

    The class ``generated`` is the default for ``produce`` steps; for any step
    we honour an explicit ``class`` field if present.
    """
    outs = []
    for s in produces(recipe):
        step_class = s.get("class")
        if step_class is None:
            # Default per spec: produce steps default to "generated".
            step_class = "generated"
        if step_class == "generated":
            outs.append(s["output"])
    return outs


def _inputs(recipe: Dict[str, Any]) -> List[str]:
    """Return the list of pinned input filenames for *recipe*.

    If an ``inputs_manifest`` is declared the manifest file is read and its
    entries are returned; otherwise the ``inputs`` array is used.  The function
    never raises ``ClaimError`` for missing optional fields – an empty list is
    returned when no inputs are declared.
    """
    claim = recipe.get("claim", {})
    base = recipe.get("__base", "")
    manifest = claim.get("inputs_manifest")
    if isinstance(manifest, str):
        return _read_input_manifest(base, manifest)
    inputs = claim.get("inputs", [])
    if isinstance(inputs, list):
        # Ensure they are strings (validation already performed in load_recipe).
        return [i for i in inputs if isinstance(i, str)]
    return []

# The public names required by the seam test.
__all__ = [
    "load_recipe",
    "recipe_path",
    "_steps",
    "gates",
    "produces",
    "generated_outputs",
    "_inputs",
    "_read_input_manifest",
]
