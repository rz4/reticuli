"""Read a claim's current state for the command line."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(directory, name):
    """Return optional JSON residue, leaving a missing or damaged file unknown."""
    path = os.path.join(directory, kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except (OSError, UnicodeError, ValueError):
        return None


def _verified(directory):
    try:
        return kernel.verify(directory)
    except kernel.ClaimError as exc:
        return {"ok": False, "error": str(exc)}


def _gate_ok(audit):
    return bool(audit and audit.get("ok"))


def _verdict(verified, audit=None):
    if not verified.get("ok"):
        return "identity mismatch"
    if audit is None:
        return "unmeasured"
    return "earned" if _gate_ok(audit) else audit.get("verdict", "carried or broken")


def _phase(directory):
    return kernel.phase(directory)


def _signatures(directory):
    """List present signature statements without claiming they are trusted."""
    folder = os.path.join(directory, kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))
    except OSError:
        return []


def _deciding_words(recipe):
    words = []
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            words.extend(kernel.gate_deciders(step["run"]))
    return list(dict.fromkeys(words))


def _next_step(view):
    """Name the next action in the draft → sealed → signed ladder."""
    if view.get("phase") == "draft":
        return "seal"
    if view.get("verified") is False:
        return "restore pinned bytes and verify"
    if view.get("phase") == "signed":
        return "audit"
    if view.get("proof_recorded"):
        return "sign"
    return "crosscheck"


def _claim_view(directory):
    parsed = kernel.load_recipe(directory)
    name = parsed["claim"]["name"]
    phase = _phase(directory)
    manifest = kernel.read_manifest(directory) if phase != "draft" else None
    checked = _verified(directory) if manifest else None
    view = {"name": name, "root": manifest["root"] if manifest else None,
            "phase": phase, "verified": checked.get("ok") if checked else None,
            "proof_recorded": bool(manifest and manifest.get("proof")),
            "signatures": _signatures(directory),
            "deciders": _deciding_words(parsed),
            "cost": kernel.cost(directory),
            "mutation_score": _read_residue(directory, "mutation_score.json")}
    view["next"] = _next_step(view)
    return view
