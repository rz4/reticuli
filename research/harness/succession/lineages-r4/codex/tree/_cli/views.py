"""Read claim state for the CLI without changing claim bytes."""

from __future__ import annotations

import json
import os

from .. import kernel
from .._kernel import recipe as recipe_tools


def _read_residue(directory, name):
    """Read optional JSON residue, treating absent or damaged data as unknown."""
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
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
    return kernel.phase(directory)


def _signatures(directory):
    folder = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sign.json"))


def _gate_ok(gates):
    return bool(gates) and all(isinstance(row, dict) and row.get("status") in
                               ("ok", "reproduced") for row in gates)


def _verdict(view):
    if not view.get("verified"):
        return "mismatch" if view.get("phase") != "draft" else "unsealed"
    audit = view.get("audit")
    if isinstance(audit, dict):
        return audit.get("verdict", "earned" if audit.get("ok") else "unearned")
    return "identity verified"


def _deciding_words(view):
    verdict = _verdict(view)
    return f"{view.get('phase', 'draft')}: {verdict}"


def _next_step(view):
    """Name the next useful command in the claim's evidence ladder."""
    if view.get("phase") == "draft":
        return "seal"
    if not view.get("verified"):
        return "restore pinned bytes and verify"
    if not (view.get("audit") or {}).get("ok"):
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    if view.get("phase") != "signed":
        return "sign"
    return "verify"


def _claim_view(directory):
    """Summarize a claim's identity, local evidence, and next action."""
    directory = os.path.abspath(os.fspath(directory))
    parsed = kernel.load_recipe(directory)
    phase = _phase(directory)
    checked = _verified(directory) if phase != "draft" else None
    manifest = kernel.read_manifest(directory) if phase != "draft" else {}
    outputs = recipe_tools.generated_outputs(parsed)
    present = [name for name in outputs if os.path.isfile(os.path.join(directory, name))]
    view = {
        "name": parsed["claim"]["name"],
        "path": directory,
        "root": manifest.get("root"),
        "phase": phase,
        "verified": bool(checked and checked.get("ok")),
        "generated": {"present": present,
                      "missing": [name for name in outputs if name not in present]},
        "proof": manifest.get("proof"),
        "signatures": _signatures(directory),
        "audit": _read_residue(directory, "audit.json"),
        "cost": kernel.cost(directory),
    }
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
