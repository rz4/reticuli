"""Read claim state for the command-line status and next-step views."""

from __future__ import annotations

import os

from .. import kernel


def _phase(directory: str) -> str:
    return kernel.phase(directory)


def _verified(directory: str) -> dict | None:
    """Return the identity comparison, or None before a claim is sealed."""
    if _phase(directory) == "draft":
        return None
    return kernel.verify(directory)


def _read_residue(directory: str) -> dict:
    """Read optional manifest and cost evidence without judging gates."""
    if _phase(directory) == "draft":
        return {"proof": None, "cost": None}
    manifest = kernel.read_manifest(directory)
    return {"proof": manifest.get("proof"), "cost": kernel.cost(directory)}


def _signatures(directory: str) -> list[str]:
    base = os.path.join(directory, kernel.SIGN_DIR)
    if not os.path.isdir(base):
        return []
    return sorted(name for name in os.listdir(base) if name.endswith(".sign.json"))


def _gate_ok(verdict: dict | None) -> bool:
    if not isinstance(verdict, dict):
        return False
    gates = verdict.get("gates", [])
    return bool(verdict.get("ok")) and all(
        row.get("status") in ("ok", "reproduced") for row in gates)


def _verdict(directory: str) -> dict:
    """Earn current gate verdicts for a sealed claim."""
    return kernel.audit(directory)


def _deciding_words(view: dict) -> str:
    if view.get("phase") == "draft":
        return "draft claim"
    if view.get("verified") is False:
        return "identity mismatch"
    if view.get("phase") == "signed":
        return "signed claim"
    if view.get("proof"):
        return "proof recorded"
    return "sealed claim"


def _next_step(view: dict) -> str:
    """Name the next useful rung from the state already in a claim view."""
    if view.get("phase") == "draft":
        return "seal"
    if view.get("verified") is False:
        return "restore pinned bytes, then verify"
    if not view.get("proof"):
        return "crosscheck"
    if view.get("phase") != "signed":
        return "sign"
    return "audit"


def _claim_view(directory: str) -> dict:
    """Read a claim into a compact, documented state dictionary."""
    recipe = kernel.load_recipe(directory)
    phase = _phase(directory)
    checked = _verified(directory)
    residue = _read_residue(directory)
    view = {"name": recipe["claim"]["name"],
            "root": checked["root"] if checked else None,
            "phase": phase,
            "verified": checked["ok"] if checked else None,
            "proof": residue["proof"],
            "cost": residue["cost"],
            "signatures": _signatures(directory)}
    view["status"] = _deciding_words(view)
    view["next"] = _next_step(view)
    return view
