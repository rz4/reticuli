"""Measure a claim's test strength with deterministic mutation probes."""

from __future__ import annotations

from . import kernel


def assess(directory, mutants=100):
    """Report measured, unmeasured, and inapplicable evidence separately."""
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a non-negative integer")
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    audit = kernel.audit(directory)
    result = {"root": checked["root"], "audit": audit,
              "measured": {}, "not_measured": {}, "not_applicable": {}}
    recipe = kernel.load_recipe(directory)
    generated = [step["output"] for step in recipe.get("step", [])
                 if step["kind"] == "produce"
                 and step.get("class", "generated") == "generated"
                 and "from" not in step]
    if not audit.get("ok"):
        result["not_measured"]["mutation"] = "baseline gates did not pass"
    elif mutants == 0:
        result["not_measured"]["mutation"] = "no mutants requested"
    elif not any(name.endswith(".py") for name in generated):
        result["not_applicable"]["mutation"] = "no generated Python source"
    else:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            result["measured"]["mutation"] = score
        else:
            result["not_applicable"]["mutation"] = "no applicable mutations"
    return result
