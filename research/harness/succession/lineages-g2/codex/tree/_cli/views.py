"""Read a claim into a compact state and suggest its next action."""

from __future__ import annotations

import json
import os

from .. import kernel


def _read_residue(directory, name):
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _verified(directory):
    try:
        return kernel.verify(directory)
    except kernel.ClaimError:
        return None


def _gate_ok(directory):
    """A recorded audit is only a hint; callers may explicitly re-audit."""
    residue = _read_residue(directory, "audit.json")
    return bool(isinstance(residue, dict) and residue.get("ok") is True)


def _signatures(directory):
    folder = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))


def _phase(directory):
    return kernel.phase(directory)


def _verdict(view):
    if not view.get("verified", False):
        return "identity mismatch" if view.get("root") else "unsealed"
    if view.get("gate_ok"):
        return "earned"
    return "unmeasured"


def _deciding_words(view):
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal the claim"
    if not view.get("verified", True):
        return "restore the pinned bytes or seal a new claim"
    if phase == "signed":
        return "audit the signed claim"
    if not view.get("proof"):
        return "crosscheck the claim on three machines"
    return "sign the proven claim"


def _next_step(view):
    return _deciding_words(view)


def _claim_view(directory):
    """Return the documented claim state without executing its gates."""
    parsed = kernel.load_recipe(directory)
    verified = _verified(directory)
    manifest = _read_residue(directory, "manifest.json")
    root = verified.get("root") if verified else (manifest or {}).get("root")
    try:
        phase = _phase(directory)
    except kernel.ClaimError:
        phase = "sealed" if manifest else "draft"
    view = {"name": parsed["claim"]["name"], "root": root,
            "phase": phase, "verified": bool(verified and verified.get("ok")),
            "proof": (manifest or {}).get("proof"),
            "signatures": _signatures(directory),
            "gate_ok": _gate_ok(directory)}
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
