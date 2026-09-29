"""Rebuild a sealed claim in a fresh directory and re-earn its gates."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any

from . import core, recipe, run, seal


def _authorized(directory: str) -> bool:
    """A build is authorized by an intact, present seal."""
    try:
        return bool(seal.verify(directory)["ok"])
    except (core.ClaimError, OSError, ValueError, KeyError):
        return False


def _compare_pin(original: str, rebuilt: str, name: str) -> bool:
    """Compare the exact bytes of a claimed file in two workspaces."""
    left = core._safe(original, name)
    right = core._safe(rebuilt, name)
    return (os.path.isfile(left) and os.path.isfile(right)
            and core._hash_file(left) == core._hash_file(right))


def _materialize(directory: str, destination: str) -> dict[str, Any]:
    """Copy only recipe inputs and generated products into a fresh workspace."""
    data = recipe.load_recipe(directory)
    recipe_name = os.path.basename(recipe.recipe_path(directory))
    names = [recipe_name, *recipe._inputs(data), *recipe.generated_outputs(data)]
    for name in dict.fromkeys(names):
        source = core._safe(directory, name)
        if not os.path.isfile(source):
            raise core.ClaimError(f"build file missing: {name}")
        core._copy_into(source, core._safe(destination, name))
    return data


def _step_guidance(step: dict[str, Any]) -> str:
    """Return the producer's requested work, if supplied."""
    return str(step.get("request", ""))


def _read_usage(directory: str) -> dict[str, Any]:
    """Read optional build usage, treating an absent record as empty."""
    path = core._safe(directory, core.USAGE)
    try:
        with open(path, encoding="utf-8") as source:
            value = json.load(source)
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise core.ClaimError("usage must be a JSON object")
    return value


def _ssh_verify(*args: Any, **kwargs: Any) -> bool:
    """No SSH attestation is required by the local claim format."""
    return False


def _produce(directory: str, destination: str, step: dict[str, Any]) -> str:
    """Carry a claimed generated product into the clean build workspace."""
    name = step["output"]
    source = core._safe(directory, name)
    if not os.path.isfile(source):
        raise core.ClaimError(f"generated output missing: {name}")
    target = core._safe(destination, name)
    core._copy_into(source, target)
    return target


def audit(directory: str) -> dict[str, Any]:
    """Verify the seal and run each gate again against a clean materialization."""
    result: dict[str, Any] = {"ok": False, "gates": [], "verdict": "unverified"}
    try:
        verification = seal.verify(directory)
        result["seal"] = verification
        if not verification["ok"]:
            result["verdict"] = "seal changed"
            return result

        with tempfile.TemporaryDirectory(prefix="reticuli-build-") as rebuilt:
            data = _materialize(directory, rebuilt)
            for name in recipe._inputs(data):
                if not _compare_pin(directory, rebuilt, name):
                    result["verdict"] = f"input changed during build: {name}"
                    return result

            for step in recipe.gates(data):
                name = step["output"]
                outcome = run.run_gate(step["run"], rebuilt, step.get("timeout"))
                gate = {"output": name, **outcome}
                output = core._safe(rebuilt, name)
                if gate["status"] == "ok" and not os.path.isfile(output):
                    gate["status"] = "missing"
                if gate["status"] == "ok":
                    original = core._safe(directory, name)
                    if os.path.isfile(original):
                        gate["status"] = ("reproduced" if _compare_pin(directory, rebuilt, name)
                                          else "changed")
                result["gates"].append(gate)
                if gate["status"] not in ("ok", "reproduced"):
                    result["verdict"] = f"gate {name} {gate['status']}"
                    return result

        result["ok"] = True
        result["verdict"] = "reproduced"
        return result
    except (core.ClaimError, OSError, ValueError, KeyError) as exc:
        result["verdict"] = str(exc)
        return result
