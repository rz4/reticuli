"""Read a claim into a compact, presentation-ready state view."""

from __future__ import annotations

import json
import os

from .. import kernel
from .._util import safe_path


def _read_residue(directory, name, default=None):
    """Read optional JSON residue without treating its absence as a failure."""
    path = safe_path(directory, name)
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read residue {name}: {exc}") from exc


def _signatures(directory):
    """List signature files associated with a claim."""
    folder = safe_path(directory, kernel.SIGN_DIR)
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder) if name.endswith(".sig"))


def _verified(directory):
    """Return the kernel's identity verdict, including its sealed root."""
    return kernel.verify(directory)


def _gate_ok(gate):
    return gate.get("status") in ("ok", "reproduced")


def _verdict(view):
    if not view.get("sealed", False):
        return "unsealed"
    if not view.get("verified", False):
        return "mismatch"
    if view.get("audit") is not None:
        return "earned" if view["audit"].get("ok") else "carried or broken"
    return "identity verified"


def _phase(view):
    if isinstance(view, (str, os.PathLike)):
        return kernel.phase(view)
    if not view.get("sealed", False):
        return "draft"
    if not view.get("verified", False):
        return "drifted"
    return view.get("phase", "sealed")


def _deciding_words(view):
    """Summarize the facts that determine the next action."""
    if not view.get("verified", False):
        return "claim identity does not match its seal"
    if view.get("missing_generated"):
        return "generated outputs are absent"
    if view.get("phase") == "signed":
        return "claim is signed"
    if view.get("proof"):
        return "crosscheck proof is recorded"
    return "claim identity is verified"


def _next_step(view):
    """Choose the next rung in the claim lifecycle."""
    phase = _phase(view)
    if phase == "draft":
        return "seal"
    if phase == "drifted":
        return "restore pinned bytes and verify"
    if view.get("missing_generated"):
        return "rebuild"
    if not view.get("audited", False):
        return "audit"
    if not view.get("proof"):
        return "crosscheck"
    if phase != "signed":
        return "sign"
    return "verify"


def _claim_view(directory):
    """Describe identity, realization, and available proof without running gates."""
    directory = os.path.realpath(directory)
    parsed = kernel.load_recipe(directory)
    claim = parsed["claim"]
    manifest_path = safe_path(directory, ".reticuli/manifest.json")
    sealed = os.path.isfile(manifest_path)
    checked = _verified(directory) if sealed else None
    manifest = kernel.read_manifest(directory) if sealed else {}
    phase = kernel.phase(directory) if not sealed or checked["ok"] else "drifted"
    generated = [step["output"] for step in parsed.get("step", [])
                 if step.get("kind") == "produce"
                 and step.get("class", "generated") in ("generated", "free")]
    missing = [name for name in generated if not os.path.isfile(safe_path(directory, name))]
    view = {
        "name": claim["name"],
        "path": directory,
        "root": manifest.get("root"),
        "phase": phase,
        "sealed": sealed,
        "verified": bool(checked and checked["ok"]),
        "generated": generated,
        "missing_generated": missing,
        "proof": manifest.get("proof"),
        "components": manifest.get("components", []),
        "signatures": _signatures(directory),
        "audited": False,
    }
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
