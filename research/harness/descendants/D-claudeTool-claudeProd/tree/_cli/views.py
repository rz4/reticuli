"""Reading a claim into the state a view renders.

Everything here READS. No view executes a gate, materializes a room, or moves
a byte: `status` is instant on any claim, and a verdict is earned by `audit`.
The ladder (`next`) is the one judgement a view makes -- the first rung this
claim has not yet earned.
"""
import os

from .. import assess as _assess
from .. import kernel
from .. import registry
from .._util import read_json

#: Where an audit leaves its dated receipt. Residue: outside every root.
RECEIPT = ".reticuli/audit.json"


def _phase(claim: str) -> str:
    try:
        return kernel.phase(claim)
    except kernel.ClaimError:
        return "broken"


def _verified(claim: str):
    try:
        return kernel.verify(claim)
    except kernel.ClaimError:
        return None


def _gate_ok(row: dict) -> bool:
    return bool(row) and row.get("status") == "ok"


def _verdict(judged: dict) -> str:
    return (judged or {}).get("verdict") or "unknown"


def _read_residue(claim: str) -> dict:
    """The receipts a claim carries: an audit's, and a measurement's.

    Both are dated testimony about a particular root, so a receipt whose root
    has moved is dropped rather than shown beside bytes it never judged.
    """
    checked = _verified(claim)
    receipt = read_json(os.path.join(claim, RECEIPT))
    if not isinstance(receipt, dict) or not checked \
            or receipt.get("root") != checked["recomputed"]:
        receipt = None
    try:
        measured = _assess.recorded(claim)
    except kernel.ClaimError:
        measured = None
    return {"audit": receipt, "assess": measured}


def _signatures(claim: str) -> dict:
    """Both drawers: an attestation and an authorization are different acts.

    A freshly signed claim once read `signed none` because the count looked in
    one drawer only.
    """
    rows = []
    for relative, act in ((".reticuli/attest", "attestation"),
                          (kernel.SIGN_DIR, "authorization")):
        drawer = os.path.join(claim, relative)
        if not os.path.isdir(drawer):
            continue
        for name in sorted(os.listdir(drawer)):
            if name.endswith(".attest.json") or name.endswith(".sign.json"):
                rows.append({"act": act, "statement": name})
    return {"count": len(rows), "statements": rows}


def _deciding_words(claim: str, parsed: dict) -> list:
    """What actually decides the verdict: the files the gates read."""
    from ..authoring import _imported
    deciding = []
    for gate in kernel.gates(parsed):
        for decider in kernel.gate_deciders(gate.get("run") or ""):
            if decider not in deciding:
                deciding.append(decider)
            for inner in _imported(claim, decider):
                if inner not in deciding:
                    deciding.append(inner)
    return deciding


def _claim_view(claim: str) -> dict:
    """A sealed claim as every view reads it."""
    checked = _verified(claim)
    parsed = None
    try:
        parsed = kernel.load_recipe(claim)
    except kernel.ClaimError:
        parsed = None
    manifest = None
    try:
        manifest = kernel.read_manifest(claim)
    except kernel.ClaimError:
        manifest = None
    table = (parsed or {}).get("claim") or {}
    residue = _read_residue(claim)
    view = {
        "path": claim,
        "name": (checked or {}).get("name") or table.get("name") or "-",
        "root": (checked or {}).get("root")
                or (manifest or {}).get("root") or "-",
        "recomputed": (checked or {}).get("recomputed"),
        "ok": bool(checked and checked["ok"]),
        "identity": "fresh" if (checked and checked["ok"]) else "broken",
        "changed": (checked or {}).get("changed") or [],
        "phase": _phase(claim),
        "declared": list(table.get("inputs") or []),
        "generated": kernel.generated_outputs(parsed) if parsed else [],
        "deciding": _deciding_words(claim, parsed) if parsed else [],
        "audited": residue["audit"],
        "measured": residue["assess"],
        "proof": (manifest or {}).get("proof"),
        "components": (manifest or {}).get("components") or [],
        "signatures": _signatures(claim),
        "cost": None, "discovery": None,
        "vacuous": kernel.vacuous_gates(parsed) if parsed else [],
    }
    try:
        view["cost"] = kernel.cost(claim)
        view["discovery"] = kernel.discovery(claim)
    except kernel.ClaimError:
        pass
    view["next"] = _next_step(view)
    return view


def _next_step(view: dict) -> str:
    """The confidence ladder: the first rung this claim has not yet earned."""
    path = view.get("path") or "."
    if not view.get("ok"):
        return (f"restore the files that moved, or reseal what you meant: "
                f"ret pack {path}")
    if view.get("vacuous"):
        return (f"declare the check as a criterion: a vacuous gate pins "
                f"nothing ({', '.join(str(v) for v in view['vacuous'])})")
    if not view.get("audited"):
        return f"re-earn the verdict cold: ret audit {path}"
    if not view.get("measured"):
        return f"measure what the tests prove: ret assess {path}"
    if not view.get("proof"):
        return (f"prove it independently: ret crosscheck {path} <rebuild>")
    if view.get("phase") != "signed":
        return f"authorize it: ret sign {path} --key <key> --as <you>"
    return "nothing: this claim is signed, proven, and measured"


def _structure(claim: str, ws=None) -> dict:
    """The claim and everything beneath it."""
    return registry.structure(claim, ws)
