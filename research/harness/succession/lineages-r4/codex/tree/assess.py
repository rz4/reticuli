"""Measure how much of a claim's generated implementation its gates check."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=10):
    """Report mutation evidence in measured, missing, and inapplicable buckets."""
    parsed = kernel.load_recipe(directory)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    generated = [step["output"] for step in parsed.get("step", [])
                 if step["kind"] == "produce" and step.get("class", "generated") == "generated"]
    gates = [step for step in parsed.get("step", []) if step["kind"] == "gate"]
    score = kernel.mutation_score(directory, max_mutants=mutants)
    measured = {"mutation": score, "gates": len(gates)} if score["mutants"] else {}
    not_measured = []
    if not gates:
        not_measured.append("no gates")
    if generated and not score["mutants"]:
        not_measured.append("no applicable mutants sampled")
    not_applicable = [] if generated else ["no generated outputs"]
    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
