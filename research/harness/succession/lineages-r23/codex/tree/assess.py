"""Measure the evidence supplied by a sealed claim's acceptance checks."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Report earned checks and mutation coverage, keeping unknowns explicit."""
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a nonnegative integer")
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")

    recipe = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    measured = {}
    not_measured = {}
    not_applicable = {}

    gates = [step for step in recipe.get("step", []) if step["kind"] == "gate"]
    if gates:
        measured["gates"] = audit["gates"]
    else:
        not_applicable["gates"] = "claim declares no gates"

    if mutants == 0:
        not_measured["mutation_score"] = "mutation probes were disabled"
    else:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            measured["mutation_score"] = score
        else:
            not_applicable["mutation_score"] = "no eligible mutations"

    return {"root": verified["root"], "ok": bool(audit.get("ok")),
            "measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
