"""Reading a sealed claim into the documented state dict `cli.py` renders,
and the ladder of what to run next.

`_claim_view` never runs a gate -- it is a read (identity, phase,
recipe-declared gates and their deciders, signatures present on disk), not
a verdict. `_next_step` names the next rung of the ladder (`spec/
verification.md`'s phases: draft -> sealed -> signed) from a view already
built. Imports only the kernel's pinned surface (`reticuli.kernel`),
never a `_kernel` private (`spec/layers.md`).
"""
import os

from .. import kernel

# draft -> sealed -> signed: what closes the gap to the next rung.
_LADDER = {
    "draft": "seal the claim to compute its root (ret seal)",
    "sealed": "run the three-machine crosscheck (ret crosscheck)",
    "signed": "nothing further -- the claim is signed and proven",
}


def _phase(d):
    """The claim's phase (`kernel.phase`): `draft` / `sealed` / `signed`.
    A claim with a manifest that no longer verifies is reported `sealed`
    rather than raising -- the view degrades to "sealed, but see
    `verified`", not a crash.
    """
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "sealed"


def _verified(d):
    """Whether `d`'s identity currently holds against its sealed
    manifest. `False`, never a raised error, when verification itself
    cannot complete (a missing manifest, an unreadable pinned input).
    """
    try:
        return kernel.verify(d)["ok"]
    except kernel.ClaimError:
        return False


def _gate_ok(status):
    """Whether a gate status string counts as passing (`spec/record.md`'s
    status vocabulary: only `"ok"` does).
    """
    return status == "ok"


def _deciding_words(deciders):
    """A human phrase naming what decides a gate: its workspace deciders
    (`kernel.gate_deciders`), joined; or, when there are none, a note that
    the recipe's own pinned run text decides it.
    """
    if not deciders:
        return "the recipe's own pinned text"
    return ", ".join(deciders)


def _signatures(d):
    """The signature-statement names present under the claim's sign
    directory (`kernel.SIGN_DIR`), sorted; empty when none exist or the
    directory is absent.
    """
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    suffix = ".sign.json"
    return sorted(
        name[: -len(suffix)] for name in os.listdir(sign_dir) if name.endswith(suffix)
    )


def _read_residue(d, name):
    """Read a JSON residue file under the claim's store (`kernel.STORE`)
    by its name relative to the store, e.g. `"mutation_score.json"`.
    `None` when it is absent or unreadable -- residue is never required
    for a view to render.
    """
    import json

    path = os.path.join(d, kernel.STORE, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _verdict(view):
    """A one-word summary of the claim's standing: `unverified` when its
    identity does not currently hold, otherwise its phase.
    """
    if not view.get("verified"):
        return "unverified"
    return view.get("phase", "draft")


def _next_step(view):
    """The next rung of the ladder for a claim already read into `view`:
    what closes the gap between its current phase and `signed`.
    """
    phase = view.get("phase", "draft")
    return _LADDER.get(phase, _LADDER["draft"])


def _claim_view(d):
    """Read the claim at `d` into the documented state dict: `name`,
    `root`, `phase`, `verified`, the declared `gates` and what decides
    each, `signatures` present on disk, `cost` from the ledger, an overall
    `verdict`, and `next` -- the ladder's next rung. Never runs a gate.
    """
    manifest = kernel.read_manifest(d)
    parsed = kernel.load_recipe(d)

    gates = []
    for step in parsed.get("step", []):
        if step.get("kind") != "gate":
            continue
        deciders = kernel.gate_deciders(step.get("run", ""))
        gates.append({
            "output": step["output"],
            "deciders": deciders,
            "decided_by": _deciding_words(deciders),
        })

    view = {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": _phase(d),
        "verified": _verified(d),
        "gates": gates,
        "signatures": _signatures(d),
        "cost": kernel.cost(d),
    }
    view["verdict"] = _verdict(view)
    view["next"] = _next_step(view)
    return view
