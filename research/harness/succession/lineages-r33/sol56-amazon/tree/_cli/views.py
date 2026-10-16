"""Presentation-neutral views over a claim's current state.

These helpers do not execute gates.  They combine recipe, manifest, residue,
and trust observations into ordinary dictionaries that a text or JSON surface
can render without changing the underlying semantics.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from reticuli import kernel


def _read_residue(d: Any, name: str | None = None, default: Any = None) -> Any:
    """Read JSON residue beneath ``.reticuli``; malformed residue is absent.

    ``name`` may also be a claim-relative path.  Residue is diagnostic and
    must never make an otherwise readable claim view fail.
    """
    if name is None:
        name = "mutation_score.json"
    path = os.fspath(name)
    if not os.path.isabs(path):
        portable = path.replace("\\", "/")
        if portable == ".reticuli" or portable.startswith(".reticuli/"):
            path = os.path.join(os.fspath(d), path)
        else:
            path = os.path.join(os.fspath(d), kernel.STORE, path)
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value
    except (OSError, UnicodeError, ValueError, TypeError):
        return default


def _gate_ok(value: Any) -> bool:
    """Whether gate/audit data says every declared gate was re-earned."""
    if isinstance(value, str):
        return value in {"ok", "reproduced", "earned"}
    if isinstance(value, Mapping):
        if value.get("ok") is False:
            return False
        if "status" in value and not _gate_ok(value.get("status")):
            return False
        if "gates" in value:
            return _gate_ok(value.get("gates"))
        return value.get("ok") is True or value.get("verdict") == "earned"
    if isinstance(value, (list, tuple)):
        return all(_gate_ok(item) for item in value)
    return False


def _verified(value: Any) -> bool:
    """Whether identity verification data holds."""
    if isinstance(value, Mapping):
        return value.get("ok") is True
    return value is True


def _verdict(value: Any) -> str:
    """Return a concise verdict word for an audit/crosscheck result."""
    if not isinstance(value, Mapping):
        return "unknown"
    verdict = value.get("verdict")
    if isinstance(verdict, str) and verdict:
        return verdict
    if value.get("satisfied") is True:
        return "accept"
    if value.get("ok") is True:
        return "earned"
    if value.get("satisfied") is False:
        return "reject"
    if value.get("ok") is False:
        return "broken"
    return "unknown"


def _signatures(d: Any, manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Summarize signature files and whether they currently confer trust."""
    directory = os.path.join(os.fspath(d), kernel.SIGN_DIR)
    files: list[str] = []
    try:
        files = sorted(name for name in os.listdir(directory)
                       if name.endswith((".sign.json", ".sig", ".sign")))
    except OSError:
        pass

    trusted = False
    anchor = os.environ.get("RETICULI_SIGNERS")
    if anchor:
        # ``phase`` is the kernel's authoritative combination of trusted
        # authorization and recorded proof.  Keep failures diagnostic-only.
        try:
            trusted = kernel.phase(d) == "signed"
        except kernel.ClaimError:
            trusted = False
    identities: list[str] = []
    for filename in files:
        if not filename.endswith(".sign.json"):
            continue
        value = _read_residue(d, os.path.join(kernel.SIGN_DIR, filename))
        if isinstance(value, Mapping) and isinstance(value.get("identity"), str):
            if value["identity"] not in identities:
                identities.append(value["identity"])
    return {"present": bool(files), "trusted": trusted,
            "files": files, "identities": identities}


def _deciding_words(view: Any) -> list[str]:
    """Name the facts which currently decide a claim view."""
    if not isinstance(view, Mapping):
        return ["unreadable"]
    words: list[str] = []
    phase = view.get("phase")
    if isinstance(phase, str):
        words.append(phase)
    verification = view.get("verification")
    if verification is not None:
        words.append("identity holds" if _verified(verification) else "identity mismatch")
    audit = view.get("audit")
    if audit is not None:
        words.append("gates earned" if _gate_ok(audit) else "gates unearned")
    proof = view.get("proof")
    if proof:
        words.append("crosscheck recorded")
    signatures = view.get("signatures")
    if isinstance(signatures, Mapping) and signatures.get("trusted"):
        words.append("trusted signature")
    return words or ["unknown"]


def _phase(d: Any, manifest: Mapping[str, Any] | None = None) -> str:
    """Read phase while keeping malformed/unsealed state representable."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        if manifest is not None:
            return "sealed"
        return "draft"


def _next_step(view: Any) -> str:
    """Return the next rung in the claim lifecycle as an actionable sentence."""
    if not isinstance(view, Mapping):
        return "inspect the claim refusal"
    if view.get("error"):
        return "repair the claim so its recipe can be read"
    phase = view.get("phase", "draft")
    verification = view.get("verification")
    if phase == "draft":
        return "seal the claim"
    if verification is not None and not _verified(verification):
        return "restore the sealed identity"
    audit = view.get("audit")
    if audit is not None and not _gate_ok(audit):
        return "audit and repair the realization"
    if not view.get("proof"):
        return "crosscheck the claim on three machines"
    signatures = view.get("signatures")
    if not (isinstance(signatures, Mapping) and signatures.get("trusted")):
        return "sign the proven claim with a trusted key"
    return "publish or use the signed claim"


def _claim_view(d: Any, *, audit: bool = False) -> dict[str, Any]:
    """Read a claim into the documented state dictionary.

    Required lifecycle keys are always present for a readable claim: ``name``,
    ``root``, ``phase``, and ``next``.  Identity verification is cheap and is
    included for sealed claims; gate execution occurs only when explicitly
    requested with ``audit=True``.
    """
    directory = os.path.abspath(os.fspath(d))
    try:
        recipe = kernel.load_recipe(directory)
    except kernel.ClaimError as exc:
        view: dict[str, Any] = {
            "path": directory, "name": os.path.basename(directory),
            "root": None, "phase": "draft", "error": str(exc),
        }
        view["next"] = _next_step(view)
        view["deciding"] = _deciding_words(view)
        return view

    name = recipe["claim"]["name"]
    manifest: Mapping[str, Any] | None = None
    verification: Mapping[str, Any] | None = None
    try:
        manifest = kernel.read_manifest(directory)
        verification = kernel.verify(directory)
    except kernel.ClaimError:
        manifest = None

    root = (verification or manifest or {}).get("root")
    phase = _phase(directory, manifest)
    proof = manifest.get("proof") if isinstance(manifest, Mapping) else None
    view = {
        "path": directory,
        "name": name,
        "root": root,
        "phase": phase,
        "verification": verification,
        "verified": _verified(verification),
        "proof": proof,
        "signatures": _signatures(directory, manifest),
        "cost": kernel.cost(directory),
        "mutation_score": _read_residue(directory),
    }
    if audit:
        view["audit"] = kernel.audit(directory)
    view["next"] = _next_step(view)
    view["deciding"] = _deciding_words(view)
    return view


__all__ = ["_claim_view", "_deciding_words", "_gate_ok", "_next_step",
           "_phase", "_read_residue", "_signatures", "_verdict", "_verified"]
