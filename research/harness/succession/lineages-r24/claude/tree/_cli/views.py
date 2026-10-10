"""Reading a sealed claim into the small state dict a surface displays
(spec/layers.md "surface"). Every function here reads what the kernel
already computed; none of them touch identity -- `_claim_view` is a
report, not a second verifier.
"""
import json
import os

from reticuli import kernel

_LADDER = {
    "draft": "seal this claim: ret seal",
    "sealed": "earn a verdict: ret crosscheck",
    "signed": "fully signed; nothing further to do",
}


def _phase(d: str) -> str:
    """`draft` / `sealed` / `signed` -- a thin wrapper so a view never
    calls into the kernel package directly."""
    return kernel.phase(d)


def _verified(d: str) -> bool:
    """Whether the bytes present still recompute to the sealed root; a
    claim with no manifest yet (still `draft`) is reported unverified
    rather than raising."""
    try:
        return kernel.verify(d)["ok"]
    except kernel.ClaimError:
        return False


def _gate_ok(status: str) -> bool:
    """Whether a gate's status counts as a pass (`spec/verification.md`
    pins the failure classes; the passing spelling is `ok`)."""
    return status == "ok"


def _deciding_words(step: dict) -> str:
    """A human-readable account of which files decide one gate step."""
    deciders = kernel.gate_deciders(step.get("run", "") or "")
    if not deciders:
        return "decided by: (nothing legible)"
    return "decided by: " + ", ".join(deciders)


def _read_residue(d: str, name: str):
    """Parsed JSON from one file under the claim's store, or `None` when
    it is absent or unreadable -- residue is never required to exist."""
    path = os.path.join(d, kernel.STORE, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _signatures(d: str) -> list:
    """The signature statement filenames present in the claim's sign
    directory, sorted, or `[]` when there are none yet."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    return sorted(f for f in os.listdir(sign_dir) if f.endswith(".sign.json"))


def _verdict(result) -> str:
    """The three-valued crosscheck verdict (`accept`/`reject`/`incomplete`)
    out of a crosscheck result, or `incomplete` for anything else -- an
    unmeasured verdict is never guessed at as a pass."""
    if isinstance(result, dict) and "verdict" in result:
        return result["verdict"]
    return "incomplete"


def _next_step(view: dict) -> str:
    """The next rung of the `draft -> sealed -> signed` ladder, in words."""
    phase = view.get("phase", "draft")
    if phase == "sealed" and not view.get("verified", True):
        return "re-seal: the present bytes no longer match the sealed root"
    return _LADDER.get(phase, _LADDER["draft"])


def _claim_view(d: str) -> dict:
    """A sealed claim's documented state: identity, phase, its gates and
    their deciders, any signatures present, and the next rung to climb."""
    manifest = kernel.read_manifest(d)
    parsed = kernel.load_recipe(d)
    phase = _phase(d)
    verified = _verified(d)
    gates = [
        {"output": step["output"], "deciders": _deciding_words(step)}
        for step in parsed.get("step", []) or []
        if step.get("kind") == "gate"
    ]

    view = {
        "name": manifest["name"],
        "root": manifest["root"],
        "phase": phase,
        "verified": verified,
        "gates": gates,
        "vacuous": kernel.vacuous_gates(parsed),
        "signatures": _signatures(d),
    }
    view["next"] = _next_step(view)
    return view
