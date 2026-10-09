"""CLI views: read a sealed claim into the documented state dict, and
derive the `next` rung on the ladder a human would climb from here.

Every function here only reads what is already on disk -- the recipe, the
manifest, the ledger, the signature directory. None of them run a gate
(that is `audit`'s job, the only verb that re-earns a verdict) and none
recompute a hash beyond what `kernel.verify`/`kernel.phase` already do;
a view reports carried state, not earned truth (`spec/verification.md`).

Stdlib only; built from `reticuli.kernel` and `reticuli._util` alone, so
no layer here reaches past the kernel's public boundary (`spec/layers.md`).
"""
import os

from reticuli import kernel, _util


def _phase(d: str) -> str:
    """The claim's phase, tolerant of drift: `kernel.phase` raises when a
    sealed claim no longer verifies, but a view must still show *something*
    for a drifted claim rather than crash while reading it.
    """
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "drifted"


def _verified(d: str) -> bool:
    """Whether the bytes present still recompute to the sealed root."""
    try:
        return bool(kernel.verify(d)["ok"])
    except kernel.ClaimError:
        return False


def _gate_steps(doc: dict) -> list:
    return [s for s in doc.get("step", []) if s.get("kind") == "gate"]


def _gate_ok(d: str, doc: dict) -> dict:
    """Per gate step, whether its pinned verdict file is present on disk.

    Presence, not re-earned truth: a view reads carried state without
    running anything, so a gate can show here as "present" and still fail
    a cold `audit`.
    """
    result = {}
    for step in _gate_steps(doc):
        output = step["output"]
        try:
            path = _util.safe_path(d, output)
        except kernel.ClaimError:
            result[output] = False
            continue
        result[output] = os.path.isfile(path)
    return result


def _verdict(gate_ok: dict) -> str:
    """The three-valued vocabulary (`spec/verification.md`), read from
    carried state alone: `accept` when every gate's verdict is present,
    `reject` when at least one is missing, `incomplete` when the claim
    declares no gates to carry a verdict about.
    """
    if not gate_ok:
        return "incomplete"
    return "accept" if all(gate_ok.values()) else "reject"


def _signatures(d: str) -> list:
    """The identities with a signature statement filed under the claim's
    sign directory, sorted. Read, not cryptographically re-checked here --
    `kernel.phase` is what decides whether any of them are trusted.
    """
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    suffix = ".sign.json"
    return sorted(
        name[: -len(suffix)]
        for name in os.listdir(sign_dir)
        if name.endswith(suffix)
    )


def _read_residue(d: str) -> dict:
    """A small summary of the claim's residue: how many ledger events it
    carries, and cost totals where any unit was measured.
    """
    events = kernel.ledger_events(d)
    summary = {"ledger_events": len(events)}
    totals = kernel.cost(d)
    if totals:
        summary["cost"] = totals
    return summary


def _deciding_words(ok: bool, phase: str) -> str:
    """The one-voice phrase describing a claim's state: plain, factual,
    composed into a human-readable line alongside its name.
    """
    if phase == "drifted":
        return "has drifted from its sealed root"
    if phase == "draft":
        return "is not yet sealed"
    if not ok:
        return "does not hold"
    return f"holds, phase {phase}"


def _next_step(view: dict) -> str:
    """The next rung on the ladder this view's claim stands on
    (`spec/verification.md`'s verbs): `draft` -> seal it; `drifted` ->
    find out why with `verify`; a sealed claim with no recorded proof ->
    `crosscheck` it; a sealed claim with a proof -> `sign` it; a signed
    claim has one rung left, re-earning it cold with `audit`.
    """
    phase = view.get("phase")
    if phase == "draft":
        return "seal"
    if phase == "drifted":
        return "verify"
    if phase == "signed":
        return "audit"
    if view.get("proof"):
        return "sign"
    return "crosscheck"


def _claim_view(d: str) -> dict:
    """Read sealed claim `d` into the documented state dict: `name`,
    `root`, `phase`, `verified`, `gates`, `verdict`, `signatures`,
    `residue`, `proof`, and `next` -- the rung `_next_step` names for it.
    """
    manifest = kernel.read_manifest(d)
    doc = kernel.load_recipe(d)
    phase = _phase(d)
    gate_ok = _gate_ok(d, doc)
    view = {
        "name": manifest["name"],
        "root": manifest["root"],
        "phase": phase,
        "verified": _verified(d),
        "gates": gate_ok,
        "verdict": _verdict(gate_ok),
        "signatures": _signatures(d),
        "residue": _read_residue(d),
        "proof": manifest.get("proof"),
    }
    view["next"] = _next_step(view)
    return view
