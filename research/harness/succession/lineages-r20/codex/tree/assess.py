"""Measure what a claim's checks establish on its present build."""

from __future__ import annotations

from . import kernel


def assess(directory, mutants=100):
    """Return measured, unmeasured, and inapplicable assessment buckets.

    The identity and cold gate audit are separate observations. Mutation
    testing is meaningful only when there are locally generated outputs.
    """
    parsed = kernel.load_recipe(directory)
    verified = kernel.verify(directory)
    audited = kernel.audit(directory)
    measured = {"identity": verified, "audit": audited}
    not_measured = {}
    not_applicable = {}
    generated = [step for step in parsed.get("step", [])
                 if step.get("kind") == "produce"
                 and step.get("class", "generated") in ("generated", "free")
                 and "from" not in step]
    if generated:
        if audited.get("ok") and mutants > 0:
            measured["mutation"] = kernel.mutation_score(directory, max_mutants=mutants)
        else:
            not_measured["mutation"] = "cold audit failed or no mutants requested"
    else:
        not_applicable["mutation"] = "no locally generated outputs"
    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
