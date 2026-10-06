"""Read claim state for the CLI without changing claim identity."""

from __future__ import annotations

import json
import os
from typing import Any

from reticuli import kernel


def _read_residue(directory: str, name: str) -> Any:
    """Read optional JSON residue; a missing or malformed file has no value."""
    path = os.path.join(os.fspath(directory), kernel.STORE, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def _verified(directory: str) -> bool:
    try:
        return bool(kernel.verify(directory)["ok"])
    except (kernel.ClaimError, OSError):
        return False


def _gate_ok(result: Any) -> bool:
    if isinstance(result, dict):
        if "gates" in result:
            return bool(result.get("ok") and all(_gate_ok(row) for row in result["gates"]))
        return result.get("status") in ("ok", "reproduced")
    return False


def _phase(directory: str) -> str:
    return kernel.phase(directory)


def _signatures(directory: str) -> list[str]:
    path = os.path.join(os.fspath(directory), kernel.SIGN_DIR)
    try:
        return sorted(name for name in os.listdir(path) if name.endswith(".sign.json"))
    except OSError:
        return []


def _verdict(view: dict[str, Any]) -> str:
    if not view.get("verified", True):
        return "identity mismatch"
    if view.get("phase") == "draft":
        return "unsealed"
    return "earned" if view.get("gate_ok") else "not audited"


def _deciding_words(view: dict[str, Any]) -> str:
    return _verdict(view)


def _next_step(view: dict[str, Any]) -> str:
    """Name the next actionable rung in a claim's lifecycle."""
    if view.get("phase") == "draft":
        return "seal"
    if not view.get("verified", True):
        return "restore pinned bytes and verify"
    if not view.get("gate_ok"):
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    if view.get("phase") != "signed":
        return "sign"
    return "verify"


def _claim_view(directory: str) -> dict[str, Any]:
    """Summarize a claim using the public kernel reads and optional residue."""
    parsed = kernel.load_recipe(directory)
    name = parsed["claim"]["name"]
    manifest_path = os.path.join(os.fspath(directory), kernel.MANIFEST)
    if os.path.isfile(manifest_path):
        manifest = kernel.read_manifest(directory)
        checked = kernel.verify(directory)
        phase = kernel.phase(directory) if checked["ok"] else "sealed"
        root = manifest["root"]
        verified = bool(checked["ok"])
        proof = manifest.get("proof")
    else:
        phase, root, verified, proof = "draft", None, False, None
    view = {"name": name, "root": root, "phase": phase,
            "verified": verified, "proof": proof,
            "signatures": _signatures(directory), "gate_ok": False}
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
