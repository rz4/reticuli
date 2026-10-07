"""reticuli._cli.views: a sealed claim, read into a plain state dict.

`_claim_view` is the one entry point the surface layer's commands share:
name, root, phase, and the documented keys around them (whether the
claim still verifies, its signatures, its mutation residue if any), plus
`next` -- the ladder's next rung, named by `_next_step` from the view
alone. Everything else here is a small reader `_claim_view` composes
from `reticuli.kernel`'s public surface; nothing in this module touches
a kernel private.

Stdlib only.
"""
import os

from reticuli import kernel

_LADDER = ("seal", "audit", "sign", "pack")


def _phase(d: str) -> str:
    """`kernel.phase`, verbatim -- the one place this module names it,
    so every caller reads the same three-way phase."""
    return kernel.phase(d)


def _verified(d: str) -> bool:
    """Whether `d` still verifies; a refusal (missing/malformed claim)
    reads as not verified rather than raising past this reader."""
    try:
        return kernel.verify(d)["ok"]
    except kernel.ClaimError:
        return False


def _gate_ok(status: str) -> bool:
    """Whether a gate's reported status counts as passing."""
    return status == "ok"


def _read_residue(d: str, name: str):
    """A JSON residue file under the claim's store (e.g. the mutation
    score), or `None` when it is absent or unreadable -- residue is
    always optional context, never load-bearing for a view."""
    import json
    path = os.path.join(d, kernel.STORE, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _signatures(d: str) -> list:
    """The identities of every signature statement filed under the
    claim's sign directory, sorted for a stable display order."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    names = [n[: -len(".sign.json")] for n in os.listdir(sign_dir) if n.endswith(".sign.json")]
    return sorted(names)


def _deciding_words(cmd: str) -> str:
    """A one-line human gloss of `kernel.gate_deciders(cmd)`."""
    deciders = kernel.gate_deciders(cmd)
    if not deciders:
        return "decided by nothing claimed (vacuous)"
    return "decided by " + ", ".join(deciders)


def _verdict(result) -> str:
    """A one-word gloss of an audit/crosscheck result dict, or
    `"unknown"` when there is no result to read yet."""
    if not isinstance(result, dict):
        return "unknown"
    if result.get("ok") or result.get("satisfied"):
        return "accept"
    return result.get("verdict", "reject")


def _next_step(view: dict) -> str:
    """The ladder's next rung, named from the view alone -- always a
    non-empty string, since a claim always has a next thing to do."""
    phase = view.get("phase")
    if phase == "draft":
        return "seal"
    if phase == "signed":
        return "pack"
    if phase == "sealed":
        if not view.get("verified", True):
            return "seal"
        if view.get("audited"):
            return "sign"
        return "audit"
    return "seal"


def _claim_view(d: str) -> dict:
    """Read the claim at `d` into the documented state dict: at least
    `name`, `root`, `phase`, `next`, plus the context behind them."""
    phase = _phase(d)
    view = {"path": d, "phase": phase, "name": None, "root": None}
    if phase != "draft":
        manifest = kernel.read_manifest(d)
        view["name"] = manifest.get("name")
        view["root"] = manifest.get("root")
        view["verified"] = _verified(d)
        view["signatures"] = _signatures(d)
        view["mutation"] = _read_residue(d, "mutation_score.json")
        view["audited"] = bool(manifest.get("proof"))
    view["next"] = _next_step(view)
    return view
