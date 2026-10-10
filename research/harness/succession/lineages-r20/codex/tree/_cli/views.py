"""Read a claim into a concise command line state view."""

from __future__ import annotations

import json
import os

from .. import kernel


def _read_residue(directory, name):
    """Read optional JSON residue; absent or malformed files carry no claim."""
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _verified(directory):
    """Report whether the sealed identity still matches its pinned bytes."""
    try:
        return kernel.verify(directory)
    except kernel.ClaimError:
        return {"ok": False, "root": None}


def _phase(directory):
    return kernel.phase(directory)


def _signatures(directory):
    """List locally stored signature statements without treating them as trust."""
    folder = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))
    except OSError:
        return []


def _gate_ok(gate):
    return isinstance(gate, dict) and gate.get("status") in ("ok", "reproduced")


def _verdict(directory):
    """Return any recorded proof; an audit is needed to earn a fresh verdict."""
    try:
        return kernel.read_manifest(directory).get("proof")
    except kernel.ClaimError:
        return None


def _deciding_words(view):
    """Summarize the facts that determine the next action."""
    if not view.get("verified", {}).get("ok", False) and view.get("phase") != "draft":
        return "identity mismatch"
    if view.get("phase") == "draft":
        return "unsealed draft"
    if view.get("phase") == "signed":
        return "trusted signature and recorded proof"
    if view.get("proof"):
        return "proof recorded; signature pending"
    return "sealed identity"


def _next_step(view):
    """Name one useful next rung in the claim lifecycle."""
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal"
    if not view.get("verified", {}).get("ok", True):
        return "restore pinned bytes and verify"
    if phase == "signed":
        return "audit"
    if view.get("proof"):
        return "sign"
    return "audit, then crosscheck"


def _claim_view(directory):
    """Collect a sealed claim's identity, evidence, and next action."""
    parsed = kernel.load_recipe(directory)
    phase = _phase(directory)
    verified = _verified(directory) if phase != "draft" else {"ok": False, "root": None}
    proof = _verdict(directory) if phase != "draft" else None
    view = {"name": parsed["claim"]["name"], "root": verified.get("root"),
            "phase": phase, "verified": verified, "proof": proof,
            "signatures": _signatures(directory)}
    view["status"] = _deciding_words(view)
    view["next"] = _next_step(view)
    return view
