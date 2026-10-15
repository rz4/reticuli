"""Reading a sealed claim into the CLI's state dict -- see `spec/layers.md`.

`_claim_view` turns a claim directory into the dict the CLI renders:
identity, phase, the declared gates, any signatures, any mutation-score
residue, and the one `next` rung the status ladder names. Reaches only
`reticuli.kernel`'s pinned public surface and `reticuli._util`'s shared
helpers -- never a `reticuli._kernel` private. Stdlib only.
"""
import os

from reticuli import _util, kernel


def _phase(d: str) -> str:
    """`kernel.phase`, defaulting to `draft` rather than raising."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _verified(d: str) -> dict:
    """`kernel.verify`, as a dict even when the claim cannot be verified."""
    try:
        return kernel.verify(d)
    except kernel.ClaimError as e:
        return {"ok": False, "error": str(e)}


def _gate_ok(view: dict) -> bool:
    """Whether the identity this view reports still holds."""
    return bool((view.get("verified") or {}).get("ok"))


def _deciding_words(run_cmd: str) -> str:
    """A human phrase naming what a gate's run command decides by."""
    deciders = kernel.gate_deciders(run_cmd)
    if not deciders:
        return "decided by the command itself"
    if len(deciders) == 1:
        return f"decided by {deciders[0]}"
    return "decided by " + ", ".join(deciders[:-1]) + f" and {deciders[-1]}"


def _read_residue(d: str) -> dict:
    """The mutation-score residue (`spec/kernel-api.md`), or `None` -- a
    claim that was never scored carries no residue, which is not a
    refusal."""
    path = os.path.join(d, kernel.STORE, "mutation_score.json")
    if not os.path.isfile(path):
        return None
    try:
        return _util.read_json(path)
    except kernel.ClaimError:
        return None


def _signatures(d: str) -> list:
    """Every signature statement under the claim's sign directory, as the
    `{identity, proof_recorded}` pairs the view renders. Not a
    re-verification of the signature chain -- `kernel.phase` already
    decided `signed` or not."""
    mdir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(mdir):
        return []
    out = []
    for fn in sorted(os.listdir(mdir)):
        if not fn.endswith(".sign.json"):
            continue
        try:
            stmt = _util.read_json(os.path.join(mdir, fn))
        except kernel.ClaimError:
            continue
        identity_name = stmt.get("identity")
        if identity_name:
            out.append({"identity": identity_name,
                        "proof_recorded": bool(stmt.get("proof_recorded"))})
    return out


def _verdict(view: dict) -> str:
    """One word for the claim's overall standing: `draft`, `broken`, or
    the phase itself once the identity it reports holds."""
    phase = view.get("phase", "draft")
    if phase == "draft":
        return "draft"
    return phase if _gate_ok(view) else "broken"


def _next_step(view: dict) -> str:
    """The one next rung the CLI's `next` ladder names for this view."""
    verdict = _verdict(view)
    if verdict == "draft":
        return "seal"
    if verdict == "broken":
        return "fix the drifted bytes, then verify"
    if verdict == "sealed":
        return "crosscheck or sign"
    if verdict == "signed":
        return "crosscheck"
    return "verify"


def _claim_view(d: str) -> dict:
    """A claim directory, read into the state dict the CLI renders."""
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        parsed = {}
    name = parsed.get("claim", {}).get("name", "?")

    verified = _verified(d)
    root = verified.get("root")
    if root is None:
        try:
            root = kernel.read_manifest(d).get("root")
        except kernel.ClaimError:
            root = None

    gates = []
    for step in parsed.get("step", []):
        if step.get("kind") != "gate":
            continue
        gates.append({"output": step.get("output"),
                      "deciding": _deciding_words(step.get("run", ""))})

    view = {
        "name": name,
        "root": root,
        "phase": _phase(d),
        "verified": verified,
        "gates": gates,
        "signatures": _signatures(d),
        "residue": _read_residue(d),
    }
    view["next"] = _next_step(view)
    return view
