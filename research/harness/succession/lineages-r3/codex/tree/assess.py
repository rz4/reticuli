"""Measure the strength of a claim's present acceptance checks."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Audit the build and sample deterministic mutations of generated Python.

    The result separates measurements from evidence this method did not
    collect and measurements that cannot apply to this claim.
    """
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a non-negative integer")
    audit = kernel.audit(directory)
    measured = {"audit": audit}
    not_measured = ["heldout"]
    not_applicable = []
    if audit.get("ok"):
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            measured["mutation"] = score
        else:
            not_applicable.append("mutation")
    else:
        not_measured.append("mutation")
    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
