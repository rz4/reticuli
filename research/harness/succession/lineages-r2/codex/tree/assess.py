"""Measure how strongly a claim's tests constrain its generated Python."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Report measured evidence and explicitly identify missing instruments."""
    parsed = kernel.load_recipe(directory)
    generated = [step for step in parsed.get("step", [])
                 if step.get("kind") == "produce"
                 and step.get("class", "generated") in ("generated", "free")]
    measured = {}
    not_measured = {}
    not_applicable = {}

    if generated:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            measured["mutation"] = score
        else:
            not_applicable["mutation"] = "no Python mutants available"
    else:
        not_applicable["mutation"] = "claim has no generated outputs"

    not_measured["heldout"] = "no held-out criteria supplied"
    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
