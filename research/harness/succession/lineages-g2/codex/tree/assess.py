"""Measure the evidence a claim's present implementation earns."""

from __future__ import annotations

from . import kernel


def assess(directory, *, mutants=100):
    """Audit the claim and probe generated Python with deterministic mutants.

    The three buckets distinguish a measurement from one that could not be
    made, and from one for which the claim has no applicable subject.
    """
    measured = {}
    not_measured = {}
    not_applicable = {}

    try:
        identity = kernel.verify(directory)
    except kernel.ClaimError as exc:
        not_measured["identity"] = str(exc)
        return {"measured": measured, "not_measured": not_measured,
                "not_applicable": not_applicable}

    measured["identity"] = identity
    if not identity["ok"]:
        not_measured["audit"] = "claim identity does not match its seal"
        not_measured["mutation"] = "claim identity does not match its seal"
        return {"measured": measured, "not_measured": not_measured,
                "not_applicable": not_applicable}

    try:
        measured["audit"] = kernel.audit(directory)
    except kernel.ClaimError as exc:
        not_measured["audit"] = str(exc)

    if mutants <= 0:
        not_applicable["mutation"] = "no mutants requested"
    else:
        try:
            score = kernel.mutation_score(directory, max_mutants=mutants)
            if score["mutants"]:
                measured["mutation"] = score
            else:
                not_applicable["mutation"] = "no applicable generated Python mutants"
        except kernel.ClaimError as exc:
            not_measured["mutation"] = str(exc)

    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
