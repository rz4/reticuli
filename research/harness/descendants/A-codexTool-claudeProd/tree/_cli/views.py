"""Reading a claim, or a session, into a state dict — and the ladder.

`status` is the PURE view: it reads and reports, never executes.  Every form
of it is instant, which is only possible because nothing here runs a gate —
a verdict is earned by `audit`, and this module reports what was earned
before, dated and named as testimony rather than as fact.

The **ladder** is the other half.  Every view ends with `next`: the first
rung this claim has not yet earned.  The rungs advance exactly when the
evidence appears — an audit leaves a receipt, `assess` leaves root-stamped
measurements, a crosscheck leaves a proof, a trusted signature leaves an
authorization — and residue is read only while the root still matches, since
a measurement of a claim that has since moved is a measurement of something
else.
"""
import os

from .. import kernel


def _verified(claim: str):
    """What identity says, or None if there is no claim here."""
    try:
        return kernel.verify(claim)
    except kernel.ClaimError:
        return None


def _phase(claim: str):
    """`draft` / `sealed` / `signed`, or None if the claim is unreadable."""
    try:
        return kernel.phase(claim)
    except kernel.ClaimError:
        return None


def _read_residue(claim: str, relative: str, root: str = None):
    """Residue, read only while it still belongs to this root."""
    path = os.path.join(claim, relative)
    if not os.path.isfile(path):
        return None
    try:
        payload = kernel._read_json(path)
    except kernel.ClaimError:
        return None
    if not isinstance(payload, dict):
        return None
    if root is not None and payload.get("root") not in (None, root):
        return None
    return payload


def _signatures(claim: str) -> dict:
    """Both drawers.

    An attestation and a signing authorization live in different stores, and
    a freshly signed claim once read `signed none` because one of them was
    counted and the other was not.
    """
    attestations, authorizations = [], []
    where = os.path.join(claim, ".reticuli", "attest")
    if os.path.isdir(where):
        attestations = sorted(n for n in os.listdir(where)
                              if n.endswith(".attest.json"))
    where = os.path.join(claim, kernel.SIGN_DIR)
    if os.path.isdir(where):
        authorizations = sorted(n for n in os.listdir(where)
                                if n.endswith(".sign.json"))
    return {"attestations": len(attestations),
            "authorizations": len(authorizations),
            "total": len(attestations) + len(authorizations),
            "names": attestations + authorizations}


def _verdict(claim: str, root: str = None):
    """The dated audit receipt, if one was left on this machine."""
    return _read_residue(claim, kernel.RECEIPT, root)


def _gate_ok(view: dict) -> bool:
    """Did the last recorded audit earn every gate?"""
    receipt = view.get("audited")
    return bool(receipt and receipt.get("ok"))


def _deciding_words(view: dict) -> str:
    """What the measurement said, in words a reader can weigh."""
    deciding = view.get("deciding")
    if not deciding:
        return "strength unknown"
    score = deciding.get("mutation_score") or {}
    measured = len(deciding.get("measured") or [])
    unmeasured = len(deciding.get("not_measured") or [])
    rate = score.get("rate")
    words = f"measured {measured}, not measured {unmeasured}"
    if rate is not None:
        words += f", mutation rate {rate:.2f}"
    return words


def _next_step(view: dict) -> str:
    """The first rung this claim has not earned — the confidence ladder."""
    claim = view.get("path") or "."
    if not view.get("root"):
        return "ret pack <path> to declare a claim here"
    if not view.get("ok"):
        return (f"ret status {claim} --all to see what moved, then restore "
                f"the declared bytes (or reseal deliberately)")
    if not view.get("audited"):
        return f"ret audit {claim} to earn the verdicts on these bytes"
    if not view.get("deciding"):
        return f"ret assess {claim} to measure what the criteria prove"
    if not view.get("proof"):
        return (f"ret crosscheck {claim} <other> to prove it reproduces "
                f"independently")
    if view.get("phase") != "signed":
        return f"ret sign {claim} --key <key> to authorize the chain"
    return "nothing: this claim is signed, proven, and measured"


def _claim_view(claim: str) -> dict:
    """Everything a view needs about a sealed claim — read, never run."""
    checked = _verified(claim)
    parsed = None
    try:
        parsed = kernel.load_recipe(claim)
    except kernel.ClaimError:
        parsed = None
    root = checked["recomputed"] if checked else None
    manifest = None
    try:
        manifest = kernel.read_manifest(claim)
    except kernel.ClaimError:
        manifest = None
    view = {
        "path": claim,
        "name": (checked or {}).get("name")
        or ((parsed or {}).get("claim", {}) or {}).get("name"),
        "root": (checked or {}).get("root"),
        "recomputed": root,
        "ok": bool(checked and checked["ok"]),
        "changed": (checked or {}).get("changed") or [],
        "phase": _phase(claim),
        "audited": _verdict(claim, root),
        "deciding": _read_residue(claim, kernel.DECIDING, root),
        "proof": (manifest or {}).get("proof"),
        "components": (manifest or {}).get("components") or [],
        "signatures": _signatures(claim),
        "cost": kernel.cost(claim),
        "format": int(((parsed or {}).get("claim", {}) or {}).get(
            "format", 1) or 1),
        "files": [],
    }
    if parsed:
        fmt = view["format"]
        for name in kernel.declared_inputs(parsed, claim):
            view["files"].append({"path": name, "class": "input",
                                  "kind": "input"})
        for step in parsed.get("step", []):
            view["files"].append({
                "path": step.get("output"),
                "class": kernel.step_class(step, fmt),
                "kind": step.get("kind"), "from": step.get("from")})
    view["status"] = ("fresh" if view["ok"] else
                      ("broken" if view["root"] else "draft"))
    view["next"] = _next_step(view)
    return view
