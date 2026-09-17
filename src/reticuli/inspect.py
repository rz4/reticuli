"""Inspect: someone handed you a claim. What have you actually got?

Every other verb is written from the author's side. This one is written for
the person on the receiving end, and it answers three questions in one pass:

    what holds here          identity, gates re-earned, proof, signatures
    what this does NOT establish
    what you are trusting

The middle section is not decoration. The whole premise is that a re-runnable
record replaces "I tested it" -- and the failure mode of that premise is a
reader who sees a hash and a green verdict and concludes more than was shown.
A claim proves that an artifact satisfies some criteria; it says nothing about
whether those criteria are any good, and nothing at all about the
implementation, which is outside the root by construction. So the limits are
printed every time, beside the result, rather than living in a document the
reader may never open (docs/threat-model.md has the long version).

Verdicts are earned here, not read: the gates are re-run. That is the
difference between this and `verify`, which only says the bytes still hash to
the sealed root.
"""
from __future__ import annotations

import os

from . import attest, kernel


def inspect(claimdir: str, signers: str | None = None,
            strict: bool = True) -> dict:
    """Re-earn what can be re-earned locally, and say what remains unproven.

    Receiving is the adversarial posture, so the gates run under the STRICT
    jail by default: writes confined to the workspace, network denied, and
    the user's own files masked -- a stranger's gate should not get to read
    your home directory while you judge their claim. `strict=False` opts
    back down to the standard tier.
    """
    manifest = kernel.read_manifest(claimdir)
    recipe = kernel.load_recipe(claimdir)
    report: dict = {"name": manifest.get("name"), "root": manifest.get("root")}

    identity = kernel.verify(claimdir)
    report["identity"] = {"ok": identity["ok"], "recomputed": identity.get("recomputed")}

    verdict = kernel.audit(claimdir, strict=strict)
    report["confinement"] = {"strict": bool(strict),
                             "backend": kernel.sandbox_backend()}
    report["gates"] = {
        "ok": verdict["ok"],
        # A gate can run clean while the claim still fails: if the bytes no
        # longer hash to the sealed root, the thing being judged is not the
        # thing that was sealed, so a passing gate earns nothing.
        "claim_ok": verdict.get("claim_ok", True),
        "count": len(verdict.get("gates", [])),
        "rows": [{"output": g.get("output"), "status": g.get("status")}
                 for g in verdict.get("gates", [])],
        "environment": verdict.get("environment") or [],
    }

    proof = manifest.get("proof")
    report["proof"] = {"recorded": bool(proof), "detail": proof}

    try:
        signatures = attest.sign_check(claimdir, signers=signers)
    except kernel.ClaimError as exc:
        signatures = {"authorized": False, "statements": [], "why": str(exc)}
    report["signatures"] = {
        "authorized": bool(signatures.get("authorized")),
        "count": len(signatures.get("statements") or []),
        "anchor": bool(os.environ.get("RETICULI_SIGNERS") or signers),
    }
    report["phase"] = kernel.phase(claimdir)

    # What the reader is trusting, named concretely rather than in the abstract:
    # the pinned files that decide the gates ARE the specification, and the
    # whole result rests on whether they are any good.
    deciders: list[str] = []
    generated = set(kernel.generated_outputs(recipe))
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            deciders += [d for d in kernel.gate_deciders(step.get("run") or "")
                         if d not in generated]
    claim_table = recipe.get("claim") or {}
    report["trusting"] = {
        "criteria": sorted(set(deciders)),
        "inputs": len(claim_table.get("inputs") or []),
    }
    # The four questions a recipient actually has, answered as data: what is
    # fixed (change it and it is a different claim), what is free (rewrite
    # it and the claim keeps its name), what was demonstrated here and now,
    # and what remains unknown.
    report["fixed"] = {
        "criteria": sorted(set(deciders)),
        "inputs": report["trusting"]["inputs"],
        "requires": claim_table.get("requires") or [],
        "environment": claim_table.get("environment"),
        "envelope": claim_table.get("envelope"),
        "mutation_floor": claim_table.get("mutation_floor"),
    }
    report["free"] = {"generated": sorted(generated)}

    report["not_established"] = [
        ("that the implementation is correct or safe -- it is outside the root "
         "by design, so a backdoored implementation passing these tests would "
         "verify identically"),
        ("how strong the criteria are: `ret assess` measures that, and this "
         "does not run it"),
        ("that any producer was independent -- independence is recorded as a "
         "declaration, never proven from content"),
    ]
    if not report["signatures"]["anchor"]:
        report["not_established"].append(
            "that anyone vouched for this: you have no trust anchor "
            "configured, so no signature can be authorized to you")
    return report
