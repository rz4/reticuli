"""Reading a claim into the shapes the CLI renders: the claim-view dict a
status-style command shows, and the small readers it's built from. Every
reader here calls through `reticuli.kernel` -- never into `reticuli._kernel`
-- so this module owes the kernel nothing but its pinned surface
(spec/layers.md).
"""
import os

from .. import kernel

_LADDER = {
    "draft": "seal",
    "sealed": "crosscheck",
    "signed": "audit",
    "invalid": "rebuild",
}


def _phase(d: str) -> str:
    """`kernel.phase`, with a mismatch (a sealed claim whose bytes no
    longer verify) reported as its own word rather than raised past a
    view -- a view describes a claim, it does not refuse on its behalf."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "invalid"


def _verified(d: str) -> bool:
    """Whether the claim's identity holds against the bytes present; false
    (never raised) for a claim that cannot even be checked."""
    try:
        return bool(kernel.verify(d).get("ok"))
    except kernel.ClaimError:
        return False


def _gate_ok(gate: dict) -> bool:
    """Whether one gate record (from `verify`/`rebuild`/`audit`) counts as
    passing."""
    return bool(gate) and gate.get("status") == "ok"


def _verdict(gates: list) -> str:
    """The three-valued read of a list of gate records
    (spec/verification.md): `accept` when every gate is `ok`, `incomplete`
    when any gate's status is missing or `environment` (a hard condition
    nobody measured), `reject` otherwise."""
    if not gates:
        return "incomplete"
    statuses = [g.get("status") for g in gates]
    if all(s == "ok" for s in statuses):
        return "accept"
    if any(s is None or s == "environment" for s in statuses):
        return "incomplete"
    return "reject"


def _deciding_words(run_cmd: str) -> str:
    """Human text for `kernel.gate_deciders`: the files a gate's own
    command reads to decide its verdict, joined for display."""
    paths = kernel.gate_deciders(run_cmd)
    return ", ".join(paths) if paths else "nothing identifiable"


def _signatures(d: str) -> list:
    """The signature statements stored under the claim, by filename --
    residue the view lists but does not verify (that is `kernel.phase`'s
    job)."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    return sorted(name for name in os.listdir(sign_dir) if name.endswith(".sign.json"))


def _read_residue(d: str) -> list:
    """Every ledger entry recorded under the claim so far, in append
    order -- the cost and gate history a view can show without re-running
    anything."""
    try:
        return kernel.ledger_events(d)
    except kernel.ClaimError:
        return []


def _next_step(view: dict) -> str:
    """The ladder's next rung for a claim view, keyed by its phase; a
    phase this view does not recognize still names something to try."""
    return _LADDER.get(view.get("phase"), "seal")


def _claim_view(d: str) -> dict:
    """A sealed (or draft) claim read into the documented state dict:
    `name`, `root`, `phase`, whether it `verified`, its stored
    `signatures`, and the ladder's `next` rung."""
    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError as exc:
        view = {"name": None, "root": None, "phase": "draft",
                "verified": False, "signatures": [], "error": str(exc)}
        view["next"] = _next_step(view)
        return view

    name = (recipe.get("claim") or {}).get("name")
    phase = _phase(d)

    root = None
    if phase != "draft":
        try:
            root = kernel.read_manifest(d).get("root")
        except kernel.ClaimError:
            root = None

    view = {
        "name": name,
        "root": root,
        "phase": phase,
        "verified": _verified(d) if phase != "draft" else False,
        "signatures": _signatures(d),
    }
    view["next"] = _next_step(view)
    return view
