"""Reading a claim into the shapes the CLI surface prints: the claim
view (`_claim_view`) and the next rung on its ladder (`_next_step`).

A claim view never runs a gate -- that is `audit`'s or `rebuild`'s job,
not a status read's. It only reads what is already on disk: the
manifest, the recorded residue (ledger, signatures), and the identity
check kernel.verify already does cheaply.
"""
import json
import os

from .. import kernel

_DECIDING_WORDS = {
    "ok": "earned clean",
    "reproduced": "ran clean; pinned bytes match",
    "mismatch": "ran clean; wrong bytes",
    "failed": "nonzero exit",
    "timeout": "exceeded its wall-clock bound",
    "environment": "a declared requirement is missing on this host",
}

_NEXT_LADDER = {
    "draft": "seal the claim to compute its root",
    "sealed": "crosscheck it, or sign it once a crosscheck has passed",
    "signed": "nothing further -- signed and proven",
}


def _deciding_words(status: str) -> str:
    """A gate status, in words -- the audit vocabulary of
    `spec/verification.md`, spelled out for a human reader."""
    return _DECIDING_WORDS.get(status, status)


def _gate_ok(status: str) -> bool:
    return status == "ok"


def _phase(d: str) -> str:
    return kernel.phase(d)


def _verified(d: str) -> bool:
    try:
        return bool(kernel.verify(d)["ok"])
    except kernel.ClaimError:
        return False


def _signatures(d: str) -> list:
    """Every readable `.sign.json` statement under the claim's signature
    store, oldest filename first -- no signature verification here, only
    a listing; verification is `phase`'s job."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    out = []
    if not os.path.isdir(sign_dir):
        return out
    for fn in sorted(os.listdir(sign_dir)):
        if not fn.endswith(".sign.json"):
            continue
        try:
            with open(os.path.join(sign_dir, fn), "r", encoding="utf-8") as f:
                stmt = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(stmt, dict):
            out.append({"identity": stmt.get("identity"), "root": stmt.get("root")})
    return out


def _read_residue(d: str) -> list:
    """The claim's cost ledger, parsed one JSON object per line; absent
    or unreadable lines are skipped rather than refused -- residue is
    diagnostic, never identity."""
    events = []
    path = os.path.join(d, kernel.LEDGER)
    if not os.path.isfile(path):
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def _verdict(result: dict) -> str:
    """The three-valued crosscheck verdict (`spec/verification.md`) out
    of a result dict, defaulting to `incomplete` -- unknown evidence is
    not evidence."""
    return (result or {}).get("verdict", "incomplete")


def _next_step(view: dict) -> str:
    """The ladder: the next rung a claim at this phase should climb."""
    return _NEXT_LADDER.get(view.get("phase"), "verify the claim to see what holds")


def _claim_view(d: str) -> dict:
    """The documented state dict: name, root, phase, whether the present
    bytes still verify, known signatures, ledger residue, and the next
    rung to climb."""
    phase = _phase(d)
    manifest = kernel.read_manifest(d) if phase != "draft" else {}
    view = {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": phase,
        "verified": _verified(d) if phase != "draft" else None,
        "signatures": _signatures(d),
        "residue": _read_residue(d),
    }
    view["next"] = _next_step(view)
    return view
