"""Reading a claim into the CLI's display shapes.

`_claim_view` reads a claim directory into the documented state dict --
`name`, `root`, `phase`, the gates' last-recorded outcomes, any
signatures, residue (cost and environment, from the ledger), and `next`,
the one-rung-ahead instruction a human runs next. Everything here READS
recorded state; it never runs a gate (that is `audit`/`rebuild`'s job) --
a view is cheap and safe to print on every invocation.

`_phase`/`_verified` are thin, refusal-tolerant wrappers over
`kernel.phase`/`kernel.verify`. `_gate_ok`/`_deciding_words` turn one gate
status into a boolean and a human phrase, over the failure-class
vocabulary `spec/verification.md` pins. `_signatures` reads the signing
ceremony's directory directly (`kernel.SIGN_DIR`), verifying against
`RETICULI_SIGNERS` where that anchor is set. `_read_residue` summarizes
the ledger: cost totals, the most recent environment/producer events, and
any mutation-score file on disk. `_verdict` renders a three-valued
crosscheck/audit verdict (`accept`/`reject`/`incomplete`) with its reasons.
"""
import json
import os

from reticuli import _util
from reticuli import kernel

_SIGNERS_ENV = "RETICULI_SIGNERS"

_DECIDING_WORDS = {
    "ok": "reproduced",
    "mismatch": "wrong bytes",
    "failed": "crashed",
    "timeout": "timed out",
    "environment": "host can't judge",
}


def _phase(d: str) -> str:
    """`draft` / `sealed` / `signed` (`spec/verification.md`)."""
    return kernel.phase(d)


def _verified(d: str):
    """`kernel.verify`'s `{ok, root, recomputed}`, or `None` where there is
    nothing yet to verify (no manifest, or a malformed one)."""
    try:
        return kernel.verify(d)
    except kernel.ClaimError:
        return None


def _gate_ok(status) -> bool:
    """Whether a gate status names a passing outcome."""
    return status == "ok"


def _deciding_words(status) -> str:
    """A human phrase for one gate status (`spec/verification.md`'s
    failure classes: reproduced/mismatch/failed/timeout/environment)."""
    return _DECIDING_WORDS.get(status, str(status))


def _gates_view(d: str, recipe: dict) -> list:
    """Every gate step, with its most recently ledgered outcome (never a
    fresh run -- a view reads, it does not judge)."""
    latest = {}
    for event in kernel.ledger_events(d):
        if event.get("event") == "gate" and "output" in event:
            latest[event["output"]] = event.get("status")

    rows = []
    for step in recipe.get("step", []):
        if step.get("kind") != "gate":
            continue
        status = latest.get(step["output"])
        rows.append({
            "output": step["output"],
            "status": status,
            "ok": _gate_ok(status) if status is not None else None,
            "words": _deciding_words(status) if status is not None else "not yet run",
        })
    return rows


def _signatures(d: str) -> list:
    """Every authorization statement under `d`'s signing directory:
    identity, and whether it is anchored to `RETICULI_SIGNERS`."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []

    anchor = os.environ.get(_SIGNERS_ENV)
    anchor_ready = bool(anchor and os.path.isfile(anchor))

    out = []
    for fname in sorted(os.listdir(sign_dir)):
        if not fname.endswith(".sign.json"):
            continue
        stmt_path = os.path.join(sign_dir, fname)
        sig_path = stmt_path + ".sig"
        try:
            with open(stmt_path, "rb") as f:
                raw = f.read()
            stmt = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        identity_name = stmt.get("identity")

        anchored = False
        if anchor_ready and identity_name and os.path.isfile(sig_path):
            with open(sig_path, "rb") as f:
                signature = f.read()
            anchored = _util.ssh_verify(anchor, identity_name, kernel.SIGN_NAMESPACE,
                                         raw, signature)

        out.append({
            "identity": identity_name,
            "anchored": anchored,
            "verdict": "authorized" if anchored else "unanchored",
        })
    return out


def _read_residue(d: str) -> dict:
    """Ledger residue, summarized for display: cost totals, the most
    recent environment and producer declarations, and a mutation-score
    report, where any of those exist."""
    residue = {"cost": kernel.cost(d)}
    for event in reversed(kernel.ledger_events(d)):
        if event.get("event") == "environment" and "environment" not in residue:
            residue["environment"] = {k: event[k] for k in ("platform", "quarantine")
                                        if k in event}
        if event.get("event") == "producer" and "producer" not in residue:
            residue["producer"] = {k: event[k] for k in ("vendor", "model", "blind")
                                     if k in event}

    mutation_path = os.path.join(d, kernel.MUTATION_RESIDUE)
    if os.path.isfile(mutation_path):
        try:
            with open(mutation_path, "r", encoding="utf-8") as f:
                residue["mutation_score"] = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return residue


def _verdict(result: dict) -> str:
    """A three-valued crosscheck/audit verdict, with its reasons."""
    v = result.get("verdict")
    if v == "reject":
        reasons = result.get("rejected") or []
        return "reject: " + ", ".join(reasons) if reasons else "reject"
    if v == "incomplete":
        reasons = result.get("incomplete") or []
        return "incomplete: " + ", ".join(reasons) if reasons else "incomplete"
    return str(v)


def _next_step(view: dict) -> str:
    """The ladder's next rung, in words, from an already-built claim view."""
    phase = view.get("phase")
    if phase == "draft":
        return "seal the claim to compute its root (ret seal)"
    if phase == "sealed":
        verified = view.get("verified")
        if verified is not None and not verified.get("ok"):
            return "bytes no longer match the sealed root; investigate drift (ret verify)"
        unresolved = [g["output"] for g in (view.get("gates") or []) if not g.get("ok")]
        if unresolved:
            return "rebuild to earn gate(s): " + ", ".join(unresolved) + " (ret rebuild)"
        return "sign the claim to advance to signed (ret sign)"
    if phase == "signed":
        return "already signed; no further rung"
    return "seal the claim to compute its root (ret seal)"


def _claim_view(d: str) -> dict:
    """A claim's documented state: `name`, `root`, `phase`, its gates'
    recorded outcomes, signatures, residue, and the next ladder rung."""
    view = {"phase": _phase(d)}

    try:
        manifest = kernel.read_manifest(d)
        view["name"] = manifest["name"]
        view["root"] = manifest["root"]
    except kernel.ClaimError:
        view["root"] = None
        view["name"] = None

    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError:
        recipe = None
        view["name"] = view["name"] or None

    if recipe is not None:
        view["name"] = view["name"] or recipe.get("claim", {}).get("name")

    view["verified"] = _verified(d)
    view["gates"] = _gates_view(d, recipe) if recipe is not None else []
    view["signatures"] = _signatures(d)
    view["residue"] = _read_residue(d)
    view["next"] = _next_step(view)
    return view
