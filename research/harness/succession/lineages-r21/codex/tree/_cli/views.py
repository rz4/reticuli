"""Read claim state for the human-facing command line."""

from __future__ import annotations

import json
import os

from .. import kernel


def _read_residue(directory, name, default=None):
    path = os.path.join(directory, kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return default


def _verified(directory):
    try:
        return kernel.verify(directory)
    except (kernel.ClaimError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


def _phase(directory):
    return kernel.phase(directory)


def _gate_ok(gates):
    return all(isinstance(gate, dict) and gate.get("status") == "ok"
               for gate in gates)


def _verdict(directory):
    result = kernel.audit(directory)
    return result.get("verdict", "earned" if result.get("ok") else "broken")


def _signatures(directory):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))


def _deciding_words(view):
    if not view.get("verified", {}).get("ok", False):
        return "identity does not hold"
    if view.get("phase") == "signed":
        return "authorized and proven"
    if view.get("phase") == "sealed":
        return "identity sealed"
    return "draft claim"


def _next_step(view):
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal"
    if not view.get("verified", {}).get("ok", True):
        return "restore pinned bytes and verify"
    if phase == "signed":
        return "audit"
    if not view.get("proof"):
        return "audit, then crosscheck"
    return "sign"


def _claim_view(directory):
    """Return the claim's current identity, phase, and suggested next verb."""
    parsed = kernel.load_recipe(directory)
    verified = _verified(directory)
    try:
        phase = _phase(directory)
    except kernel.ClaimError:
        phase = "draft" if "root" not in verified else "sealed"
    root = verified.get("root")
    manifest = None
    if root:
        try:
            manifest = kernel.read_manifest(directory)
        except kernel.ClaimError:
            pass
    view = {"name": parsed["claim"]["name"], "root": root, "phase": phase,
            "verified": verified, "proof": (manifest or {}).get("proof"),
            "signatures": _signatures(directory)}
    view["next"] = _next_step(view)
    return view
