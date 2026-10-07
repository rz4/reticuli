"""Read a claim into a small, human facing state view."""

from __future__ import annotations

import json
import os

from reticuli import kernel


def _read_residue(directory, name):
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except (OSError, ValueError):
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
        return "draft" if _verified(directory) is None else "sealed"


def _gate_ok(audit):
    return isinstance(audit, dict) and audit.get("ok") is True


def _verdict(directory):
    """Return the most recent recorded proof, if there is one."""
    manifest = _read_residue(directory, "manifest.json")
    return manifest.get("proof") if isinstance(manifest, dict) else None


def _signatures(directory):
    folder = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(folder)
                      if name.endswith(".sign.json"))
    except OSError:
        return []


def _deciding_words(view):
    if not view.get("verified", False):
        return "claim identity is unverified"
    if view.get("phase") == "signed":
        return "signed claim"
    if view.get("proof"):
        return "crosscheck proof recorded"
    return "claim identity verified"


def _next_step(view):
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "seal the claim"
    if not view.get("verified", False):
        return "restore the pinned bytes and verify the claim"
    if not view.get("proof"):
        return "audit the claim, then crosscheck three machines"
    if phase != "signed":
        return "review and sign the proven claim"
    return "audit the claim when fresh evidence is needed"


def _claim_view(directory):
    parsed = kernel.load_recipe(directory)
    checked = _verified(directory)
    phase = _phase(directory)
    view = {"name": parsed["claim"]["name"],
            "root": checked.get("root") if checked else None,
            "phase": phase,
            "verified": bool(checked and checked.get("ok")),
            "proof": _verdict(directory),
            "signatures": _signatures(directory),
            "path": os.path.abspath(os.fspath(directory))}
    view["verdict"] = _deciding_words(view)
    view["next"] = _next_step(view)
    return view
