"""Assess: how much verification does a claim actually carry?

A model that writes both the implementation and the tests has verified
nothing -- the tests were fitted to the code they are supposed to judge. This
module does not answer "is the code correct". It measures how much constraint
the tests impose, on a ladder of increasing evidence and increasing cost:

    circularity     is the test that decides pass/fail itself generated?   free
    mutation        do the tests detect faults injected into the code?      seconds
    re-derivation   can a DIFFERENT model rebuild the code from the tests?  dollars
    generalization  do the tests generalise, or only enumerate?             dollars

The first two run by default; the rest are opt-in, because they spend money.

THE REPORT IS DESCRIPTIVE. It reports numbers and never converts them into a
pass or a grade: the bar belongs to the claim (`[claim] mutation_floor`, which
is pinned into identity and so travels with it) or to whoever is reading. Two
consequences shape the output:

  * An unmeasured dimension is stated, never omitted. Silence reads as
    "fine", and the difference between "not measured", "not applicable" and
    "measured: zero" is exactly the difference this tool exists to report.
  * A rate is printed with its sample and the size of the pool it was drawn
    from. Mutation rates are not comparable between programs of different size
    or structure, and a thin sample is a weak estimate no matter how precise
    the decimal looks.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel

#: How many faults to inject by default. Each costs one full re-audit, so this
#: trades seconds for a tighter estimate; the report prints the sample and the
#: candidate pool so the remaining noise stays visible.
DEFAULT_MUTANTS = 20


def _original_producer(claimdir: str) -> dict | None:
    """Who produced the implementation this claim was sealed with.

    Recorded at seal time (`ret pack --by`) as ledger residue, never in the
    root: who wrote the code is not part of what the claim demands. Without it
    a re-derivation cannot be compared against anything, so "a different model
    rebuilt it" is unverifiable.
    """
    for event in kernel.ledger_events(claimdir) or []:
        if event.get("event") == "producer" and event.get("role") == "original":
            return {"vendor": event.get("vendor"), "model": event.get("model")}
    return None


def independence_degree(original: dict | None, redo: dict | None) -> dict:
    """How far apart the two producers were -- as a degree, never a boolean.

    N-version programming assumes independently built versions fail
    independently; Knight and Leveson showed that is false even for separate
    human teams, and models from one vendor share pretraining corpora. So this
    records what was declared and leaves the weighing to the reader.
    """
    if not original or not redo or not redo.get("model"):
        return {"degree": "unknown",
                "why": "the original's producer is unrecorded"
                       if not original else "the rebuild declared no model"}
    same_model = (original.get("model") or "") == (redo.get("model") or "")
    same_vendor = (original.get("vendor") or "") == (redo.get("vendor") or "")
    if same_model:
        degree = "none"
    elif same_vendor:
        degree = "same-vendor"
    else:
        degree = "different-vendor"
    return {"degree": degree,
            "original": original, "rebuild": {"vendor": redo.get("vendor"),
                                              "model": redo.get("model")},
            "why": "declared, not established: content-independence cannot be "
                   "shown from content alone"}


def _circularity(recipe: dict) -> dict:
    """Is any gate decided by code the claim itself generates?

    A gate whose deciders are all generated outputs judges nothing: the same
    process wrote the artifact and its oracle. The kernel refuses to seal one,
    so a sealed claim passes this by construction -- but it is reported anyway,
    because for a model-written claim it is the property the reader most wants
    stated out loud.
    """
    vacuous = kernel.vacuous_gates(recipe)
    generated = set(kernel.generated_outputs(recipe))
    deciders = []
    for step in recipe.get("step", []):
        if step.get("kind") != "gate":
            continue
        for decider in kernel.gate_deciders(step.get("run") or ""):
            if decider not in generated:
                deciders.append(decider)
    return {"ok": not vacuous, "vacuous": vacuous,
            "pinned_deciders": sorted(set(deciders))}


def assess(claimdir: str, *, mutants: int = DEFAULT_MUTANTS,
           rebuild: str | None = None, rebuild_into: str | None = None) -> dict:
    """Measure a claim's strength. Cheap rungs always; costly rungs on request."""
    recipe = kernel.load_recipe(claimdir)
    manifest = kernel.read_manifest(claimdir)
    report: dict = {
        "claim": manifest.get("name"), "root": manifest.get("root"),
        "measured": {}, "not_measured": {}, "not_applicable": {}, "declared": {},
    }

    floor = (recipe.get("claim") or {}).get("mutation_floor")
    report["declared"]["mutation_floor"] = floor

    verdict = kernel.audit(claimdir)
    report["gate"] = "earned" if verdict["ok"] else "not earned"
    report["gate_detail"] = [
        {"output": g.get("output"), "status": g.get("status")}
        for g in verdict.get("gates", [])
    ]

    report["measured"]["circularity"] = _circularity(recipe)

    # -- mutation adequacy ---------------------------------------------------
    if not verdict["ok"]:
        report["not_measured"]["mutation"] = (
            "the gate does not currently pass, so a surviving mutant would mean "
            "nothing")
    else:
        score = kernel.mutation_score(claimdir, max_mutants=mutants)
        if not score.get("candidates"):
            report["not_applicable"]["mutation"] = (
                "no generated output the fault injector can read -- it mutates "
                "source text, and this claim generates none (a compiled binary, "
                "say)")
        else:
            report["measured"]["mutation"] = score

    # -- re-derivation, and independence, which only exists alongside it ------
    original = _original_producer(claimdir)
    if not rebuild:
        report["not_measured"]["re_derivation"] = (
            "no independent producer was asked to rebuild from the tests alone")
        report["not_measured"]["independence"] = (
            "nothing to compare: no rebuild was run")
    else:
        scratch = rebuild_into or tempfile.mkdtemp(prefix="reticuli-assess-")
        keep = rebuild_into is not None
        try:
            try:
                kernel.rebuild(claimdir, rebuild, scratch)
                redone = kernel.read_manifest(scratch)["root"]
                report["measured"]["re_derivation"] = {
                    "ok": redone == report["root"],
                    "root": redone,
                    "cost": kernel.cost(scratch),
                    "workspace": scratch if keep else None,
                }
            except kernel.ClaimError as exc:
                report["measured"]["re_derivation"] = {
                    "ok": False, "root": None, "error": str(exc),
                    "causes": [
                        ("the producer program itself is broken (check this "
                         "first: likeliest cause, cheapest to rule out)"),
                        "under-specification: the tests do not determine the behaviour",
                        "harness artifact: the rebuild environment differed from the gate's",
                        "capability: the producer was not strong enough",
                    ],
                    "distinguish": "retry with a stronger producer; if it lands, "
                                   "the tests were sufficient and this run measured "
                                   "capability",
                }
            redo = kernel.independence(scratch) if os.path.isdir(scratch) else None
            report["measured"]["independence"] = independence_degree(original, redo)
        finally:
            if not keep:
                shutil.rmtree(scratch, ignore_errors=True)

    report["not_measured"]["generalization"] = (
        "no held-out run: the tests were not split to see whether they "
        "generalise or only enumerate")
    return report
