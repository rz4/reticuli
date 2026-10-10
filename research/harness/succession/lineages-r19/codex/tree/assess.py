"""Measure which parts of a claim's generated implementation its gates test."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Audit the claim and report mutation evidence in three buckets.

    A killed mutant is measured, a surviving mutant is not measured, and a
    claim without mutable generated Python has no applicable mutation probe.
    """
    audit = kernel.audit(directory)
    if not audit["ok"]:
        return {"measured": [], "not_measured": [], "not_applicable": ["audit failed"],
                "audit": audit, "mutation_score": None}
    score = kernel.mutation_score(directory, max_mutants=mutants)
    survivors = set(score["survivors"])
    measured = [i for i in range(score["mutants"]) if i not in survivors]
    return {"measured": measured, "not_measured": sorted(survivors),
            "not_applicable": [] if score["mutants"] else ["no applicable mutants"],
            "audit": audit, "mutation_score": score}
