"""Read claim state for the human command line surface."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(directory, name=None):
    """Read optional JSON residue from the claim store."""
    if name is None:
        return {}
    if not isinstance(name, str) or not name or os.path.basename(name) != name:
        raise ValueError("unsafe residue name")
    path = os.path.join(directory, kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _signatures(directory):
    """List signature statements without treating their presence as trust."""
    path = os.path.join(directory, kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(path)
                      if name.endswith(".sign.json"))
    except OSError:
        return []


def _verified(directory):
    """Return the identity check, including a draft without a manifest."""
    try:
        return kernel.verify(directory)
    except kernel.ClaimError as exc:
        return {"ok": False, "root": None, "detail": str(exc)}


def _phase(directory):
    return kernel.phase(directory)


def _gate_ok(result):
    """Whether each gate in an audit earned its pinned verdict."""
    return bool(result.get("ok")) and all(
        gate.get("status") == "ok" for gate in result.get("gates", []))


def _verdict(result):
    if not result:
        return "unmeasured"
    return "earned" if _gate_ok(result) else "carried or broken"


def _deciding_words(view):
    """A short explanation of the state relevant to the next action."""
    if not view.get("verified", False):
        return "claim identity is not sealed or has changed"
    if view.get("phase") == "signed":
        return "claim is signed and proven"
    if view.get("proof"):
        return "proof is recorded; a trusted signature is needed"
    return "claim identity is sealed; audit and crosscheck can re-earn it"


def _next_step(view):
    """Return the next command in the claim's evidence ladder."""
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal"
    if not view.get("verified", True):
        return "inspect identity drift"
    if phase == "signed":
        return "audit"
    if view.get("proof"):
        return "sign"
    if view.get("audit") and not _gate_ok(view["audit"]):
        return "repair and audit"
    return "audit, then crosscheck"


def _claim_view(directory):
    """Summarize the present identity and evidence of a claim."""
    recipe = kernel.load_recipe(directory)
    checked = _verified(directory)
    phase = _phase(directory)
    manifest = None
    if phase != "draft":
        manifest = kernel.read_manifest(directory)
    view = {"name": recipe["claim"]["name"],
            "root": checked.get("root"), "phase": phase,
            "verified": bool(checked.get("ok")),
            "proof": (manifest or {}).get("proof"),
            "signatures": _signatures(directory)}
    view["next"] = _next_step(view)
    return view
