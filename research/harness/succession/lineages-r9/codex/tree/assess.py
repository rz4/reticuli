"""Measure how much of a claim's generated Python is exercised by its gates."""

from __future__ import annotations

from . import kernel


def assess(directory, mutants=100):
    """Return mutation evidence and its measured, surviving, and absent buckets.

    A killed mutant is measured by the checks; a survivor identifies behavior
    that the present checks did not distinguish.  With no applicable mutants,
    the rate is undefined rather than a perfect score.
    """
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a nonnegative integer")
    score = kernel.mutation_score(directory, max_mutants=mutants)
    count = score["mutants"]
    survivors = score["survivors"]
    return {
        "measured": score["killed"],
        "not_measured": len(survivors),
        "not_applicable": count == 0,
        "mutants": count,
        "survivors": survivors,
        "rate": score["rate"],
        "score": score,
    }
