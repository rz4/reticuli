"""Measure how strongly a claim's gates constrain its generated files."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Return a mutation score and explicit measurement buckets.

    A zero-candidate score is not evidence that the tests are strong: it
    means the mutation instrument found nothing it could exercise.
    """
    if isinstance(mutants, bool) or not isinstance(mutants, int) or mutants < 0:
        raise ValueError("mutants must be a nonnegative integer")
    recipe = kernel.load_recipe(directory)
    generated = [step["output"] for step in recipe.get("step", [])
                 if step["kind"] == "produce"
                 and step.get("class", "generated") == "generated"
                 and "from" not in step]
    gates = [step["output"] for step in recipe.get("step", [])
             if step["kind"] == "gate"]
    result = {"measured": {}, "not_measured": [], "not_applicable": []}
    if not generated:
        result["not_applicable"].append("no locally generated outputs")
    elif not gates:
        result["not_measured"].append("no gates")
    elif mutants == 0:
        result["not_measured"].append("mutation budget is zero")
    else:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            result["measured"]["mutation"] = score
        else:
            result["not_measured"].append("no supported mutants")
    return result
