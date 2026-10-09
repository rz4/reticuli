"""Read claim state and turn it into concise command line views."""

from __future__ import annotations

import json
import os

from .. import kernel


def _read_residue(path):
    """Read optional local evidence without changing the sealed identity."""
    manifest = os.path.join(os.fspath(path), kernel.MANIFEST)
    if not os.path.isfile(manifest):
        return {}
    return kernel.read_manifest(path)


def _verified(path):
    try:
        return kernel.verify(path)
    except kernel.ClaimError:
        return {"ok": False, "root": None}


def _phase(path):
    return kernel.phase(path)


def _gate_ok(gates):
    return all(gate.get("status") in ("ok", "reproduced") for gate in gates)


def _signatures(path):
    """List locally stored signature statements for display."""
    folder = os.path.join(os.fspath(path), kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    rows = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".sign.json"):
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as source:
                    rows.append(json.load(source))
            except (OSError, ValueError):
                continue
    return rows


def _verdict(view):
    if not view.get("root"):
        return "draft"
    if view.get("verified") is False:
        return "mismatch"
    if view.get("gate_ok") is False:
        return "carried or broken"
    return "earned" if view.get("gate_ok") else "unmeasured"


def _deciding_words(view):
    return _verdict(view)


def _next_step(view):
    """Name the next useful rung of the claim's evidence ladder."""
    if not view.get("root") or view.get("phase") == "draft":
        return "seal"
    if view.get("verified") is False:
        return "verify"
    if view.get("gate_ok") is not True:
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    if view.get("phase") != "signed":
        return "sign"
    return "verified"


def _claim_view(path):
    """Return the state of a claim using the kernel's public API."""
    document = kernel.load_recipe(path)
    name = document["claim"]["name"]
    manifest = _read_residue(path)
    root = manifest.get("root")
    verified = None
    if root:
        verified = bool(_verified(path).get("ok"))
    phase = _phase(path) if verified is not False else "sealed"
    view = {"name": name, "root": root, "phase": phase,
            "verified": verified, "proof": manifest.get("proof"),
            "gate_ok": None, "signatures": _signatures(path)}
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
