"""Read a claim into a stable, human-facing status view."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(path, default=None):
    """Read optional JSON residue; missing or malformed files carry no evidence."""
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, ValueError):
        return default


def _verified(directory):
    try:
        return kernel.verify(directory).get("ok") is True
    except (kernel.ClaimError, OSError):
        return False


def _phase(directory):
    return kernel.phase(directory)


def _signatures(directory):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))


def _gate_ok(audit):
    return (isinstance(audit, dict) and audit.get("ok") is True
            and all(gate.get("status") == "ok" for gate in audit.get("gates", [])))


def _verdict(directory):
    """Report recorded proof without treating it as a fresh audit."""
    try:
        manifest = kernel.read_manifest(directory)
    except (kernel.ClaimError, OSError):
        return "unmeasured"
    return "recorded" if manifest.get("proof") else "unmeasured"


def _deciding_words(view):
    if not view.get("verified", False):
        return "claim identity has not been verified"
    if view.get("phase") == "signed":
        return "trusted authorization and recorded proof"
    if view.get("proof"):
        return "crosscheck proof recorded"
    return "sealed identity verified"


def _next_step(view):
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal the claim"
    if not view.get("verified", False):
        return "restore pinned bytes and verify the claim"
    if phase == "signed":
        return "audit the claim to re-earn its verdict"
    if view.get("proof"):
        return "sign the proved claim with a trusted key"
    return "crosscheck the claim on three machines"


def _claim_view(directory):
    parsed = kernel.load_recipe(directory)
    phase = _phase(directory)
    verified = _verified(directory)
    manifest = None
    if phase != "draft" or os.path.isfile(os.path.join(directory, kernel.MANIFEST)):
        try:
            manifest = kernel.read_manifest(directory)
        except kernel.ClaimError:
            pass
    view = {"name": parsed["claim"]["name"],
            "root": manifest.get("root") if manifest else None,
            "phase": phase,
            "verified": verified,
            "proof": bool(manifest and manifest.get("proof")),
            "verdict": _verdict(directory),
            "signatures": _signatures(directory)}
    view["next"] = _next_step(view)
    return view
