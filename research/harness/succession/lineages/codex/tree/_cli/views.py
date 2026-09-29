"""Read-only summaries of claim state for the command-line interface."""

from __future__ import annotations

import json
import os
from pathlib import Path

from reticuli import kernel


def _read_residue(directory, name):
    """Read a JSON residue file if it exists and is well formed."""
    path = Path(directory, kernel.STORE, name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None


def _verified(directory):
    """Return the identity check for a sealed claim."""
    try:
        return kernel.verify(directory)
    except kernel.ClaimError:
        return {"ok": False, "root": None}


def _phase(directory):
    """Return the verifier-relative claim phase."""
    return kernel.phase(directory)


def _gate_ok(result):
    """Say whether every reported gate earned its verdict."""
    if not isinstance(result, dict):
        return False
    return bool(result.get("ok")) and all(
        gate.get("status") in ("ok", "reproduced")
        for gate in result.get("gates", [])
    )


def _signatures(directory):
    """Summarize the authorization statements present in the store."""
    folder = Path(directory, kernel.SIGN_DIR)
    if not folder.is_dir():
        return []
    return sorted(path.name for path in folder.glob("*.sign.json") if path.is_file())


def _verdict(directory):
    """Read a fresh audit of the present build."""
    return kernel.audit(directory)


def _deciding_words(view):
    """Summarize the facts that determine the next action."""
    if not isinstance(view, dict):
        return "claim unavailable"
    if not view.get("verified", False):
        return "identity changed"
    if view.get("phase") == "signed":
        return "signed claim"
    if view.get("proof"):
        return "proof recorded"
    return "sealed claim"


def _next_step(view):
    """Name the next rung in the claim workflow."""
    if not isinstance(view, dict) or view.get("phase") == "draft":
        return "seal"
    if not view.get("verified", True):
        return "restore pinned bytes and verify"
    if view.get("phase") == "signed":
        return "audit"
    if view.get("proof"):
        return "sign"
    if not view.get("generated_present", True):
        return "rebuild"
    return "audit, then crosscheck"


def _claim_view(directory):
    """Collect the documented name, root, phase, and next rung."""
    data = kernel.load_recipe(directory)
    verified = _verified(directory)
    phase = _phase(directory)
    try:
        manifest = kernel.read_manifest(directory)
    except kernel.ClaimError:
        manifest = {}
    generated = [step["output"] for step in data.get("step", [])
                 if step.get("kind") == "produce" and
                 step.get("class") == "generated"]
    view = {"name": data["claim"]["name"], "root": verified.get("root"),
            "phase": phase, "verified": bool(verified.get("ok")),
            "proof": manifest.get("proof"),
            "generated_present": all(os.path.isfile(os.path.join(directory, name))
                                     for name in generated),
            "signatures": _signatures(directory)}
    view["next"] = _next_step(view)
    return view
