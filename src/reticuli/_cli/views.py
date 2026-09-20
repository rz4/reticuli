"""ret command line — the views layer: read recorded claim state into plain dicts; verdict words; the next ladder."""
from __future__ import annotations

import json
import os

from .. import attest as attest_mod
from .. import kernel

# -- the kernel's public surface, nothing below it ---------------------------


def _phase(d: str) -> str:
    """`kernel.phase`, with a directory that holds no readable claim reported
    as `draft`. The kernel refuses a directory whose recipe or manifest it
    cannot read — a refusal is more honest than a positive an auditor would
    misread — so a surface that asks "is this a session or a claim?" absorbs
    that refusal here."""
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "draft"




def _verified(claimdir: str) -> dict:
    r = dict(kernel.verify(claimdir))
    r["phase"] = _phase(claimdir)
    return r




def _signatures(d: str) -> int:
    """How many signed statements are PRESENT on the claim — a count, not a
    verification; `ret sign --check` verifies.

    Two drawers hold statements: attestations (machine signatures over a
    build) and the signing ceremony's authorizations. Counting only the
    first made a freshly signed claim read `signed none` — found live, by
    the first user to sign one."""
    base = os.path.abspath(d)
    count = 0
    try:
        count += len([f for f in os.listdir(os.path.join(base, attest_mod.ATTEST))
                      if f.endswith(".json")])
    except OSError:
        pass
    try:
        count += len([f for f in os.listdir(os.path.join(base, attest_mod.SIGN_DIR))
                      if f.endswith(".sign.json")])
    except OSError:
        pass
    return count




def _read_residue(d: str, name: str, root) -> dict | None:
    """A store residue (an audit receipt, assess's measurements), trusted
    only while the root it stamps still matches — measurements of a
    different claim say nothing about this one."""
    try:
        with open(os.path.join(d, kernel.STORE, name), encoding="utf-8") as f:
            residue = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(residue, dict) and residue.get("root") == root:
        return residue
    return None




def _claim_view(ws: str) -> dict:
    """Everything status says about a claim, from RECORDED state only.
    A view reads; it never executes — earning verdicts is audit's identity,
    and status reporting records with honest dates is the other half of
    the same doctrine."""
    identity = kernel.verify(ws)
    recipe = kernel.load_recipe(ws)
    manifest = kernel.read_manifest(ws)
    root = manifest.get("root")
    generated = set(kernel.generated_outputs(recipe))
    deciders: list[str] = []
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            deciders += [x for x in kernel.gate_deciders(step.get("run") or "")
                         if x not in generated]
    claim_table = recipe.get("claim") or {}
    audited = _read_residue(ws, "audit.json", root)
    if audited and not audited.get("ok"):
        audited = None                    # a receipt records an EARNED verdict
    view = {
        "name": manifest.get("name"), "root": root,
        "phase": kernel.phase(ws), "ok": identity["ok"],
        "recomputed": identity.get("recomputed"),
        "changed": identity.get("changed"),
        "audited": audited,
        "deciding": _read_residue(ws, "assess.json", root),
        "discovery": (kernel.cost(ws) or {}).get("discovery"),
        "proof": bool(manifest.get("proof")),
        "signatures": _signatures(ws),
        "fixed": {"criteria": sorted(set(deciders)),
                  "inputs": len(claim_table.get("inputs") or []),
                  "inputs_list": list(claim_table.get("inputs") or []),
                  "requires": claim_table.get("requires") or [],
                  "environment": claim_table.get("environment"),
                  "envelope": claim_table.get("envelope"),
                  "mutation_floor": claim_table.get("mutation_floor")},
        "free": sorted(generated),
        "verdicts": sorted(s.get("output") for s in recipe.get("step", [])
                           if s.get("kind") == "gate" and s.get("output")),
    }
    view["next"] = _next_step(view)
    return view




def _next_step(view: dict) -> str:
    """The ladder of confidence: the first rung this claim has not earned
    is the next command. The whole product, taught one line at a time."""
    if not view["ok"]:
        return ("restore the changed files, or reseal deliberately -- "
                "a moved criterion is a different claim")
    if not view["audited"]:
        return "earn it here: ret audit ."
    if not view["deciding"]:
        return "measure the tests: ret assess ."
    if not view["proof"]:
        # --record-proof so following this line actually advances the claim:
        # a plain crosscheck decides and prints, but records nothing, and the
        # next status would repeat this same rung.
        return ("prove it: ret rebuild . --producer openai -o ../m3 "
                "&& ret crosscheck . ../m3 --record-proof")
    if not view["signatures"]:
        return "stand behind it: ret sign . --key <ssh_key> --as <you>"
    return "share it: push with the CI workflow (M2), or ret export"




def _gate_ok(g: dict) -> bool:
    """One gate's verdict. The failure classes are pinned
    (spec/verification.md); the passing spelling is implementation-defined,
    and this kernel spells it `ok`."""
    return g.get("status") == "ok"




def _verdict(r: dict) -> str:
    """One word a reviewer can act on. `earned`: every verdict reproduced.
    `environment`: a declared requirement is missing here — the verdict was
    never tested. Otherwise the gate's own failure class names it."""
    if r["ok"]:
        return "earned"
    if r.get("environment"):
        return "environment"
    bad = [g for g in r.get("gates", []) if not _gate_ok(g)]
    if not bad and r.get("layers"):            # own gates earned; a component's did not
        layer = next(g for g in r["layers"] if not g["ok"])
        return f"layer {layer['name']}: {layer['status']}"
    if bad:
        return {"mismatch": "carried or broken", "failed": "failed", "timeout": "timeout",
                "environment": "environment"}.get(bad[0].get("status", ""), "carried or broken")
    return "carried or broken" if r.get("claim_ok", True) else "broken"




def _deciding_words(view: dict) -> str:
    deciding = view.get("deciding")
    if not deciding:
        return "not measured"
    mut = deciding.get("mutation")
    if mut:
        return f"mutation {mut['rate']:.2f} ({mut['mutants']} mutants)"
    return "measured"
