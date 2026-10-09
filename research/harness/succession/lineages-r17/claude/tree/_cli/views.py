"""Reading a sealed claim into the CLI's state dict (`spec/layers.md`).

`_claim_view` is the one entry point: it reads a claim directory through
the kernel's public surface only (never a kernel private) and assembles the
documented state dict -- `name`, `root`, `phase`, `verified`, `gates`,
`signatures`, `residue`, and `next`, the ladder's recommended next rung.
The other names here are the pieces `_claim_view` composes from, each
useful on its own when a verb wants only one fact (`status` wants the
whole view; `verify` wants only `_verified`).

Stdlib only.
"""
import json
import os

from reticuli import kernel


def _phase(d: str) -> str:
    """`d`'s phase, refusing to "draft" rather than raise on a damaged claim."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"


def _verified(d: str):
    """Whether `d`'s present bytes still match its sealed root, or `None`
    when there is no sealed manifest to check against."""
    try:
        return kernel.verify(d)["ok"]
    except kernel.ClaimError:
        return None


def _deciding_words(run: str) -> list:
    """The files a gate's run line actually reads (`kernel.gate_deciders`)."""
    return kernel.gate_deciders(run or "")


def _gate_ok(d: str, step: dict) -> bool:
    """Whether a gate step's declared output is present and non-empty.

    A display-only presence check -- re-earning the verdict is `audit`'s
    job, not a view's.
    """
    output = step.get("output")
    if not output:
        return False
    path = os.path.join(d, output)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def _verdict(ok) -> str:
    """The three-valued verdict spelling (`spec/verification.md`):
    `"accept"`, `"reject"`, or `"incomplete"` for `True`/`False`/`None`."""
    if ok is True:
        return "accept"
    if ok is False:
        return "reject"
    return "incomplete"


def _signatures(d: str) -> list:
    """Signer identities found in `d`'s signature directory, sorted.

    Lists what is present on disk; it does not re-verify a signature
    against a trust anchor (that is `kernel.phase`'s job).
    """
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sign_dir):
        return []
    out = []
    for name in sorted(os.listdir(sign_dir)):
        if not name.endswith(".sign.json"):
            continue
        try:
            with open(os.path.join(sign_dir, name), "r", encoding="utf-8") as f:
                stmt = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        identity = stmt.get("identity")
        if isinstance(identity, str):
            out.append(identity)
    return out


def _read_residue(d: str):
    """Host residue a view may show: the mutation-score report and any
    recorded crosscheck proof, or `None` when neither exists yet."""
    residue = {}
    mutation_path = os.path.join(d, kernel.MUTATION_RESIDUE)
    if os.path.isfile(mutation_path):
        try:
            with open(mutation_path, "r", encoding="utf-8") as f:
                residue["mutation_score"] = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    if manifest.get("proof"):
        residue["proof"] = manifest["proof"]
    return residue or None


def _claim_view(d: str) -> dict:
    """`d` read into the documented state dict: `name`, `root`, `phase`,
    `verified`, `gates`, `signatures`, `residue`, and `next`."""
    manifest = kernel.read_manifest(d)
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        parsed = {}

    gates = []
    for step in parsed.get("step", []) if isinstance(parsed, dict) else []:
        if not isinstance(step, dict) or step.get("kind") != "gate":
            continue
        ok = _gate_ok(d, step)
        gates.append({
            "output": step.get("output"),
            "deciders": _deciding_words(step.get("run", "")),
            "ok": ok,
            "verdict": _verdict(ok),
        })

    view = {
        "name": manifest.get("name", ""),
        "root": manifest.get("root", ""),
        "phase": _phase(d),
        "verified": _verified(d),
        "gates": gates,
        "signatures": _signatures(d),
        "residue": _read_residue(d),
    }
    view["next"] = _next_step(view)
    return view


def _next_step(view: dict) -> str:
    """The ladder's recommended next rung for a claim already read into
    `view` (as `_claim_view` builds it)."""
    phase = view.get("phase")
    if phase == "draft":
        return "seal the claim"
    if view.get("verified") is False:
        return "repair drift: present bytes no longer match the sealed root"
    gates = view.get("gates") or []
    if any(not g.get("ok") for g in gates):
        return "rebuild the generated outputs until every gate passes"
    if phase == "signed":
        return "crosscheck against an independent machine"
    if not view.get("residue"):
        return "audit the claim to earn a verdict"
    if not view.get("signatures"):
        return "sign the claim"
    return "crosscheck against an independent machine"
