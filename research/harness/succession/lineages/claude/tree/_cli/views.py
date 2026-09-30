"""reticuli._cli.views -- reading a claim into the documented state dict
and the `next` ladder.

`_claim_view(d)` is the one call the `ret status`-shaped verbs build on: a
plain dict describing a claim -- its name, root, phase, gates, signatures,
and store residue -- plus `next`, a one-line suggestion of the next rung on
the ladder (`ret seal` -> `ret crosscheck` -> `ret sign` -> …). Every field
comes from `reticuli.kernel`'s own public surface; this module never reads
past the facade into `._kernel`.

Stdlib only. Never the network.
"""
import json
import os

from .. import kernel


def _phase(d: str) -> str:
    """`kernel.phase`, by name -- the ladder rung a claim currently stands
    on (`draft` / `sealed` / `signed`)."""
    return kernel.phase(d)


def _verified(d: str) -> dict:
    """`kernel.verify`, by name -- identity only, no gate re-run."""
    return kernel.verify(d)


def _verdict(d: str) -> str:
    """A one-word summary of whether the claim's identity currently holds:
    the phase it stands on, or `broken` when the sealed bytes no longer
    recompute to the manifest's root (`kernel.phase` raises exactly then)."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "broken"


def _gate_ok(status: str) -> bool:
    """Whether a gate's recorded status counts as passing. The failure
    classes are pinned (`reproduced`/`mismatch`/`failed`/`timeout`/
    `environment`, `spec/verification.md`); the passing spelling is not,
    so both the historical and the kernel's own spelling count."""
    return status in ("ok", "reproduced")


def _deciding_words(run: str) -> str:
    """A human sentence naming the files `kernel.gate_deciders` says this
    gate's `run` command actually executes."""
    deciders = sorted(kernel.gate_deciders(run))
    if not deciders:
        return "no pinned file decides this gate"
    if len(deciders) == 1:
        return f"decided by {deciders[0]}"
    return "decided by " + ", ".join(deciders[:-1]) + f" and {deciders[-1]}"


def _signatures(d: str) -> list:
    """Signature statements found in the claim's sign directory, oldest
    name first; unreadable or malformed entries are skipped rather than
    raised -- this is a display helper, not a verifier."""
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    out = []
    for fname in sorted(os.listdir(sign_dir)):
        if not fname.endswith(".sign.json"):
            continue
        try:
            with open(os.path.join(sign_dir, fname), "r", encoding="utf-8") as f:
                statement = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(statement, dict):
            out.append({"identity": statement.get("identity"), "root": statement.get("root")})
    return out


def _read_residue(d: str) -> dict:
    """A best-effort snapshot of `.reticuli/` residue that is never inside
    the root: the manifest's recorded proof, if any, and ledger cost
    totals, if any."""
    residue = {}
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    if manifest.get("proof"):
        residue["proof"] = manifest["proof"]
    totals = kernel.cost(d)
    if totals:
        residue["cost"] = totals
    return residue


_LADDER = {
    "draft": "ret seal",
    "sealed": "ret crosscheck",
    "signed": "ret claims",
    "broken": "ret verify",
}


def _next_step(view: dict) -> str:
    """The next rung on the ladder for a claim standing at `view['phase']`
    -- always a non-empty suggestion, even for a claim already at the top
    or one whose identity is broken."""
    return _LADDER.get(view.get("phase"), "ret verify")


def _claim_view(d: str) -> dict:
    """The documented state dict for the claim at `d`: `name`, `root`,
    `phase`, `verdict`, `gates`, `signatures`, `residue`, and `next`."""
    recipe = kernel.load_recipe(d)
    phase = _phase(d)
    view = {
        "name": recipe.get("claim", {}).get("name"),
        "root": None,
        "phase": phase,
        "verdict": _verdict(d),
        "gates": [],
        "signatures": [],
        "residue": {},
    }
    if phase != "draft":
        manifest = kernel.read_manifest(d)
        view["root"] = manifest.get("root")
        gate_steps = [s for s in recipe.get("step", []) if s.get("kind") == "gate"]
        view["gates"] = [
            {"output": s["output"], "deciding": _deciding_words(s.get("run", ""))}
            for s in gate_steps
        ]
        view["signatures"] = _signatures(d)
        view["residue"] = _read_residue(d)
    view["next"] = _next_step(view)
    return view
