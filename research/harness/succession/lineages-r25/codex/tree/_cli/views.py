"""Read-only claim state and suggested next actions for the command line."""

from __future__ import annotations

import json
import os

from .. import kernel


def _read_residue(directory):
    """Read optional store evidence without treating it as part of identity."""
    store = os.path.join(os.fspath(directory), kernel.STORE)
    result = {}
    for name in ("mutation_score.json", "usage.json"):
        try:
            with open(os.path.join(store, name), encoding="utf-8") as stream:
                result[name.removesuffix(".json")] = json.load(stream)
        except (OSError, ValueError):
            pass
    try:
        result["ledger"] = kernel.ledger_events(directory)
    except (OSError, ValueError, kernel.ClaimError):
        result["ledger"] = []
    return result


def _signatures(directory):
    """Describe signature evidence present in the claim store."""
    folder = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))


def _verified(directory):
    """Check the sealed identity without executing gates."""
    return kernel.verify(directory)


def _phase(directory):
    return kernel.phase(directory)


def _gate_ok(result):
    """True when every gate in a completed audit earned its verdict."""
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    return all(row.get("status") == "ok" for row in result.get("gates", []))


def _verdict(result):
    """Summarize an audit or identity result in ordinary words."""
    if not isinstance(result, dict):
        return "unknown"
    if result.get("ok") is True:
        return result.get("verdict", "verified")
    if result.get("environment"):
        return "environment"
    return result.get("verdict", "failed")


def _deciding_words(recipe):
    """Identify each gate's declared verdict and command."""
    if isinstance(recipe, (str, os.PathLike)):
        recipe = kernel.load_recipe(recipe)
    return {step["output"]: step.get("run", "")
            for step in recipe.get("step", []) if step.get("kind") == "gate"}


def _next_step(view):
    """Name the next useful rung of the claim lifecycle."""
    if view.get("phase") == "draft":
        return "seal"
    if view.get("verified") is False:
        return "restore pinned bytes, then verify"
    if view.get("materialized") is False:
        return "rebuild"
    if view.get("audit_ok") is not True:
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    if view.get("phase") != "signed":
        return "sign"
    return "audit"


def _claim_view(directory):
    """Read a claim into a stable, JSON-friendly state mapping."""
    directory = os.fspath(directory)
    recipe = kernel.load_recipe(directory)
    phase = _phase(directory)
    manifest = kernel.read_manifest(directory) if phase != "draft" else None
    checked = _verified(directory) if manifest else None
    outputs = [step["output"] for step in recipe.get("step", [])
               if step.get("kind") == "produce"
               and step.get("class", "generated") == "generated"
               and "from" not in step]
    present = all(os.path.isfile(os.path.join(directory, name)) for name in outputs)
    view = {"name": recipe["claim"]["name"],
            "root": manifest["root"] if manifest else None,
            "phase": phase,
            "verified": checked["ok"] if checked else None,
            "materialized": present,
            "generated": outputs,
            "gates": _deciding_words(recipe),
            "proof": manifest.get("proof") if manifest else None,
            "signatures": _signatures(directory),
            "residue": _read_residue(directory),
            "audit_ok": None}
    view["next"] = _next_step(view)
    return view
