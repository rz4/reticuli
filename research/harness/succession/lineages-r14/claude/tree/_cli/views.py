"""reticuli._cli.views -- reading a sealed claim into the CLI's display state.

Turns `reticuli.kernel`'s primitives into one dict a human (or `--json`)
reads about a claim -- `name`, `root`, `phase`, `verified`, `gate_ok`,
`verdict`, `signatures`, `residue` -- and the one-rung `next` ladder that
names what to do next. Nothing here is identity-bearing; it is read-only
commentary on top of the kernel.
"""
import os

from reticuli import kernel

_LADDER = {
    "draft": "seal the claim",
    "sealed": "sign the claim once its crosscheck is recorded",
    "signed": "nothing further -- the claim is signed",
}

_DECIDING_WORDS = {
    "ok": "holds",
    "mismatch": "differs",
    "failed": "failed",
    "timeout": "timed out",
    "environment": "could not run here",
}


def _phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (spec/verification.md)."""
    return kernel.phase(d)


def _verified(d: str) -> bool:
    """Does `d`'s present bytes still recompute to its sealed root? `False`
    for anything that is not even sealed yet, rather than raising."""
    try:
        return kernel.verify(d)["ok"]
    except kernel.ClaimError:
        return False


def _gate_ok(d: str) -> bool:
    """Did every gate re-earn clean on a cold audit of present bytes?"""
    try:
        return kernel.audit(d)["ok"]
    except kernel.ClaimError:
        return False


def _verdict(d: str) -> str:
    """`kernel.audit`'s own verdict word for the claim's current state
    (`earned`, `broken`, `mismatch`, `environment`)."""
    try:
        return kernel.audit(d)["verdict"]
    except kernel.ClaimError:
        return "mismatch"


def _deciding_words(status: str) -> str:
    """A short human phrase for a gate's failure-class status
    (spec/verification.md)."""
    return _DECIDING_WORDS.get(status, status)


def _signatures(d: str) -> list:
    """Every signature statement under the claim's sign directory, by
    filename. No anchor is checked here -- the view is read-only
    commentary; `kernel.phase` already does the anchored check that
    decides whether the claim counts as `signed`."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    return sorted(name for name in os.listdir(sign_dir) if name.endswith(".sign.json"))


def _read_residue(d: str) -> dict:
    """Host bookkeeping beside the claim -- ledger entry count, whether a
    crosscheck proof is recorded -- never identity-bearing."""
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    return {
        "ledger_entries": len(kernel.ledger_events(d)),
        "proof_recorded": bool(manifest.get("proof")),
    }


def _next_step(view: dict) -> str:
    """The one ladder rung a human reads next, from a view's `phase` (and,
    where sealed, whether its gates currently hold)."""
    phase = view.get("phase")
    if phase == "sealed" and view.get("verified") and not view.get("gate_ok"):
        return "rebuild: the sealed claim's gates no longer hold"
    return _LADDER.get(phase, "verify the claim: its phase could not be read")


def _claim_view(d: str) -> dict:
    """The documented state dict for a sealed claim: `name`, `root`,
    `phase`, `verified`, `gate_ok`, `verdict`, `signatures`, `residue`, and
    the `next` ladder rung computed from all of it."""
    manifest = kernel.read_manifest(d)
    view = {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": _phase(d),
        "verified": _verified(d),
        "gate_ok": _gate_ok(d),
        "verdict": _verdict(d),
        "signatures": _signatures(d),
        "residue": _read_residue(d),
    }
    view["next"] = _next_step(view)
    return view
