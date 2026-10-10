"""Read claim state and suggest the next human action."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(directory, name):
    """Read optional store JSON without treating absent residue as evidence."""
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _phase(directory):
    return kernel.phase(directory)


def _verified(directory):
    return kernel.verify(directory)


def _gate_ok(gates):
    """True only when every reported gate re-earned its verdict."""
    return all(row.get("status") in ("ok", "reproduced") for row in gates)


def _signatures(directory):
    path = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    if not os.path.isdir(path):
        return []
    return sorted(name for name in os.listdir(path) if name.endswith(".sign.json"))


def _verdict(view):
    if not view.get("verified", {}).get("ok", True):
        return "identity mismatch"
    audit = view.get("audit")
    if isinstance(audit, dict):
        return audit.get("verdict", "earned" if audit.get("ok") else "carried or broken")
    return "unmeasured"


def _next_step(view):
    """Name a useful next rung from the observed claim state."""
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal"
    if not view.get("verified", {}).get("ok", True):
        return "restore pinned bytes and verify"
    if phase == "signed":
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    return "sign"


def _deciding_words(view):
    return f"{view.get('phase', 'draft')}: {_verdict(view)}; next: {_next_step(view)}"


def _claim_view(directory):
    """Summarize the sealed identity and recorded evidence without running gates."""
    recipe = kernel.load_recipe(directory)
    name = recipe["claim"]["name"]
    phase = _phase(directory)
    if phase == "draft":
        view = {"name": name, "root": None, "phase": phase,
                "verified": None, "proof": None, "signatures": []}
    else:
        verified = _verified(directory)
        manifest = kernel.read_manifest(directory)
        view = {"name": name, "root": verified["root"], "phase": phase,
                "verified": verified, "proof": manifest.get("proof"),
                "signatures": _signatures(directory)}
    view["next"] = _next_step(view)
    return view
