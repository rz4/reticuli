"""Claim views: reading a sealed claim into the documented state dict,
and naming the next rung on the `draft` / `sealed` / `signed` ladder
(`spec/verification.md`).

`_claim_view` is read-only: it never runs a gate (that is `audit`'s and
`rebuild`'s job) and never writes to the claim. It reports what is
already on disk -- the recipe's declared gates, which validated outputs
are present, what signatures and residue exist -- and then asks
`_next_step` what a human should do next given that state. Nothing here
is identity-bearing.

Stdlib only.
"""
import os

from .. import kernel


def _phase(d: str) -> str:
    """`kernel.phase`, with a damaged or unsealed claim read as `draft`
    rather than raising -- a view must always have something to show."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _verified(d: str):
    """`kernel.verify`'s result, or `None` when the claim is not sealed
    yet (there is nothing to verify)."""
    try:
        return kernel.verify(d)
    except kernel.ClaimError:
        return None


def _signatures(d: str) -> list:
    """The names of signature statements present in the claim's sign
    directory, sorted -- empty when the claim was never signed."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    suffix = ".sign.json"
    return sorted(
        name[: -len(suffix)] for name in os.listdir(sign_dir)
        if name.endswith(suffix)
    )


def _read_residue(d: str) -> dict:
    """Which pieces of host residue (ledger, mutation score) exist under
    the claim's store -- never identity-bearing, just what has run."""
    store = os.path.join(d, kernel.STORE)
    residue = {"ledger": False, "mutation_score": False}
    if not os.path.isdir(store):
        return residue
    residue["ledger"] = os.path.isfile(os.path.join(d, kernel.LEDGER))
    residue["mutation_score"] = os.path.isfile(
        os.path.join(store, "mutation_score.json")
    )
    return residue


def _deciding_words(recipe: dict) -> dict:
    """Per gate output, the workspace files its `run` command treats as
    deciding its verdict (`kernel.gate_deciders`) -- a human-facing map
    from what a gate pins to what actually decides it."""
    words = {}
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            words[step["output"]] = kernel.gate_deciders(step.get("run", ""))
    return words


def _verdict(recipe: dict, d: str) -> list:
    """One entry per gate step, in recipe order: its output and whether
    the pinned verdict bytes are present on disk right now. This reads
    presence, not freshness -- a carried-vs-earned distinction is
    `audit`'s job, not a view's."""
    gates = []
    for step in recipe.get("step", []):
        if step.get("kind") != "gate":
            continue
        output = step["output"]
        present = os.path.isfile(os.path.join(d, output))
        gates.append({"output": output, "status": "ok" if present else "missing"})
    return gates


def _gate_ok(recipe: dict, d: str) -> bool:
    """Whether every declared gate's pinned verdict is present."""
    verdicts = _verdict(recipe, d)
    return all(g["status"] == "ok" for g in verdicts)


def _next_step(view: dict) -> str:
    """The next rung on the ladder, given a view's `phase` (and, once
    sealed, whether the bytes still verify and the gates still hold)."""
    phase = view.get("phase")
    if phase == "signed":
        return "nothing further: the claim is signed"
    if phase == "draft":
        return "seal the claim: ret seal"
    if phase == "sealed":
        if view.get("verified") is False:
            return "the bytes have drifted from the sealed root: investigate before anything else"
        if not view.get("gate_ok", True):
            return "a declared gate has no pinned verdict yet: ret rebuild"
        return "prove it independently and sign it: ret crosscheck, then ret sign"
    return "seal the claim: ret seal"


def _claim_view(d: str) -> dict:
    """The documented state dict for a claim at `d`: its name, root,
    phase, declared gates and whether each one's verdict is present,
    signatures, residue, and the next rung a human should climb."""
    recipe = kernel.load_recipe(d)
    verified = _verified(d)
    view = {
        "name": recipe["claim"]["name"],
        "root": verified["root"] if verified else None,
        "phase": _phase(d),
        "verified": verified["ok"] if verified else None,
        "gates": _verdict(recipe, d),
        "gate_ok": _gate_ok(recipe, d),
        "deciders": _deciding_words(recipe),
        "signatures": _signatures(d),
        "residue": _read_residue(d),
    }
    view["next"] = _next_step(view)
    return view
