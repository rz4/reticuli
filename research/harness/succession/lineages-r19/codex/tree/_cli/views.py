"""Read a claim's present state for CLI status displays."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, ValueError):
        return None


def _verified(directory):
    try:
        return kernel.verify(directory)
    except kernel.ClaimError:
        return None


def _phase(directory):
    try:
        return kernel.phase(directory)
    except kernel.ClaimError:
        return "draft"


def _signatures(directory):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(folder)
                      if name.endswith(".sig") and os.path.isfile(os.path.join(folder, name)))
    except OSError:
        return []


def _gate_ok(result):
    if isinstance(result, dict):
        if "ok" in result:
            return result["ok"] is True
        return result.get("status") in ("ok", "reproduced")
    return result in ("ok", "reproduced")


def _verdict(directory):
    """Read recorded proof without running gates during a status query."""
    try:
        return kernel.read_manifest(directory).get("proof")
    except kernel.ClaimError:
        return None


def _deciding_words(view):
    if isinstance(view, dict):
        return view.get("status") or view.get("phase") or "draft"
    return str(view)


def _next_step(view):
    """Name the next action in the draft → sealed → signed ladder."""
    if not isinstance(view, dict):
        return "seal"
    if view.get("phase") == "draft":
        return "seal"
    if view.get("verified") is False:
        return "restore pinned bytes, then verify"
    if view.get("phase") == "signed":
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    return "sign"


def _claim_view(directory):
    """Summarize identity and progress without re-executing claim gates."""
    parsed = kernel.load_recipe(directory)
    verified = _verified(directory)
    phase = _phase(directory)
    proof = _verdict(directory)
    view = {
        "name": parsed["claim"]["name"],
        "root": verified["root"] if verified else None,
        "phase": phase,
        "verified": bool(verified and verified.get("ok")),
        "proof": proof,
        "signatures": _signatures(directory),
    }
    view["next"] = _next_step(view)
    return view
