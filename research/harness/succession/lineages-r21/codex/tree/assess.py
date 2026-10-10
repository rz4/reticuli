"""Measure how strongly a claim's gates constrain its generated Python code."""

from __future__ import annotations

from . import kernel


def assess(directory, mutants=100):
    """Return mutation evidence in measured, unmeasured, and inapplicable buckets.

    A passing baseline is required before mutations say anything about the
    checks.  Claims without generated Python files have nothing to mutate.
    """
    parsed = kernel.load_recipe(directory)
    generated = [step["output"] for step in parsed.get("step", [])
                 if step.get("kind") == "produce"
                 and step.get("class", "generated") in ("generated", "free")
                 and "from" not in step]
    result = {"measured": {}, "not_measured": {}, "not_applicable": {}}
    if not generated:
        result["not_applicable"]["mutation"] = "no generated outputs"
        return result
    if not any(name.endswith(".py") for name in generated):
        result["not_applicable"]["mutation"] = "no generated Python outputs"
        return result
    if not kernel.verify(directory)["ok"]:
        result["not_measured"]["mutation"] = "claim identity does not hold"
        return result
    baseline = kernel.audit(directory)
    if not baseline["ok"]:
        result["not_measured"]["mutation"] = "baseline gates did not pass"
        return result
    score = kernel.mutation_score(directory, max_mutants=mutants)
    if score["mutants"]:
        result["measured"]["mutation"] = score
    else:
        result["not_applicable"]["mutation"] = "no applicable mutants"
    return result
