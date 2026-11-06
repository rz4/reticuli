"""Reading a claim into the state a view reports -- and the ladder.

A view EXECUTES NOTHING. Every number it shows was earned by some earlier
verb and left behind as residue: the audit receipt, the assessment, the
recorded proof, the statements in the two drawers. So a view is instant, it
never changes a verdict, and it is honest about the age of what it reports.

THE LADDER is the one opinionated part. Each claim has a first rung it has
not yet earned, and `next` names it: seal, then audit, then measure what the
tests prove, then prove it on three machines, then have a human sign it. The
ladder advances exactly when the EVIDENCE appears -- and stops believing a
measurement the moment the root moves away from the one it was about.
"""
import os

from .. import _util
from .. import kernel

#: what a step class MEANS to a reader of a file list
_ROLE = {"generated": "free", "pinned": "fixed", "validated": "verdict",
         "carried": "shipped"}


def _phase(claim: str) -> str:
    try:
        return kernel.phase(claim)
    except kernel.ClaimError:
        return "unknown"


def _verified(claim: str) -> dict:
    """Identity, or the reason there is none to report."""
    try:
        return kernel.verify(claim)
    except kernel.ClaimError as exc:
        return {"ok": False, "root": None, "recomputed": None,
                "name": None, "error": str(exc)}


def _read_residue(claim: str, relative: str):
    """Residue a view may read: never a verdict, always dated."""
    return _util.read_json(os.path.join(claim, relative))


def _gate_ok(row: dict) -> bool:
    return (row or {}).get("status") in ("ok", "reproduced")


def _verdict(receipt) -> dict:
    """The last audit this machine earned on this claim, if it still applies."""
    if not isinstance(receipt, dict):
        return {"when": None, "verdict": None, "ok": False}
    return {"when": receipt.get("when"), "verdict": receipt.get("verdict"),
            "ok": bool(receipt.get("ok")),
            "gates": receipt.get("gates") or []}


def _signatures(claim: str) -> dict:
    """Both drawers. A freshly signed claim once read `signed none` because
    only the attestation drawer was counted, and the ceremony's
    authorization lives in the other one."""
    found = []
    for drawer, kind in ((".reticuli/attest", "attestation"),
                         (kernel.SIGN_DIR, "authorization")):
        where = os.path.join(claim, drawer)
        if not os.path.isdir(where):
            continue
        for name in sorted(os.listdir(where)):
            if name.endswith(".attest.json") or name.endswith(".sign.json"):
                statement = _util.read_json(os.path.join(where, name)) or {}
                found.append({"kind": kind, "statement": name,
                              "identity": statement.get("identity"),
                              "when": statement.get("when")})
    return {"count": len(found), "statements": found,
            "identities": sorted({s["identity"] for s in found
                                  if s.get("identity")})}


def _deciding_words(view: dict) -> list:
    """What the last assessment DECIDED, as words a reader weighs.

    Only while the root it measured is the root present: a measurement of
    other bytes is not a measurement of these.
    """
    measured = view.get("measured")
    if not isinstance(measured, dict):
        return []
    score = measured.get("mutation_score") or {}
    words = []
    if score.get("rate") is not None:
        words.append(f"mutation {score['rate']:.2f} over "
                     f"{score.get('mutants', 0)} mutant(s)")
    for line in measured.get("measured") or []:
        words.append(line)
    return words


def _claim_view(claim: str) -> dict:
    """Everything a view of a sealed claim reports, read and never earned."""
    checked = _verified(claim)
    try:
        parsed = kernel.load_recipe(claim)
    except kernel.ClaimError:
        parsed = {"claim": {}, "step": []}
    receipt = _verdict(_read_residue(claim, kernel.RECEIPT))
    measured = _read_residue(claim, kernel.MEASURED)
    if isinstance(measured, dict) and \
            measured.get("root") != checked.get("recomputed"):
        measured = None
    manifest = {}
    try:
        manifest = kernel.read_manifest(claim)
    except kernel.ClaimError:
        manifest = {}
    totals = None
    try:
        totals = kernel.cost(claim)
    except kernel.ClaimError:
        totals = None
    files = []
    for path in _util.declared_inputs(parsed):
        files.append({"path": path, "class": "pinned", "role": "fixed"})
    for step in parsed.get("step") or []:
        klass = kernel.step_class(step)
        files.append({"path": step.get("output"), "class": klass,
                      "role": _ROLE.get(klass, klass),
                      "from": step.get("from")})
    view = {"name": checked.get("name") or manifest.get("name"),
            "root": checked.get("root"),
            "recomputed": checked.get("recomputed"),
            "ok": bool(checked.get("ok")),
            "identity": "fresh" if checked.get("ok") else "broken",
            "error": checked.get("error"),
            "changed": checked.get("changed") or [],
            "phase": _phase(claim),
            "audited": receipt,
            "measured": measured,
            "proof": manifest.get("proof"),
            "components": manifest.get("components") or [],
            "signatures": _signatures(claim),
            "cost": totals,
            "discovery": (totals or {}).get("discovery"),
            "declared": {k: v for k, v in (parsed.get("claim") or {}).items()
                         if k in ("tolerance", "envelope", "mutation_floor",
                                  "requires", "environment")},
            "files": files,
            "gates": [g.get("output") for g in kernel.gates(parsed)],
            "path": claim}
    view["deciding"] = _deciding_words(view)
    view["next"] = _next_step(view)
    return view


def _next_step(view: dict) -> str:
    """The first rung this claim has not earned. Evidence, never a mood."""
    where = view.get("path") or "."
    if not view.get("ok"):
        moved = ", ".join(view.get("changed") or []) or "the moved file(s)"
        return (f"restore {moved} to the bytes this root names, or reseal "
                f"what you meant: ret pack {where}")
    if not (view.get("audited") or {}).get("ok"):
        return f"re-earn the verdicts cold: ret audit {where}"
    if not view.get("measured"):
        return (f"measure what the tests actually prove: "
                f"ret assess {where} --mutants 20")
    if not view.get("proof"):
        return (f"prove it on three machines: "
                f"ret crosscheck {where} <rebuilt-elsewhere>")
    if view.get("phase") != "signed":
        return f"have a keyholder stand behind it: ret sign {where} --key ..."
    return "nothing: this claim is signed, proven and fresh"
