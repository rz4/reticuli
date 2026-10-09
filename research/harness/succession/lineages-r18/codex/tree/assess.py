"""Measure the evidence supplied by a claim's gates and mutation sample."""

from __future__ import annotations

from . import kernel


def assess(path, *, mutants=20):
    """Return separate measured, unmeasured, and inapplicable observations.

    An identity check and a cold audit are reported separately: a matching
    root alone does not establish that the gates pass. Mutation sampling is
    meaningful only when a generated Python output is present.
    """
    document = kernel.load_recipe(path)
    checked = kernel.verify(path)
    measured = {}
    not_measured = {}
    not_applicable = {}

    measured["identity"] = checked
    if not checked["ok"]:
        not_measured["gates"] = "claim identity does not hold"
        not_measured["mutation_score"] = "claim identity does not hold"
        return {"measured": measured, "not_measured": not_measured,
                "not_applicable": not_applicable}

    audit = kernel.audit(path)
    measured["gates"] = audit
    outputs = [step["output"] for step in document.get("step", [])
               if step["kind"] == "produce"
               and step.get("class", "generated") == "generated"
               and "from" not in step and step["output"].endswith(".py")]
    if not outputs:
        not_applicable["mutation_score"] = "no generated Python output"
    elif not audit["ok"]:
        not_measured["mutation_score"] = "gates did not pass cold audit"
    elif mutants <= 0:
        not_measured["mutation_score"] = "no mutants requested"
    else:
        measured["mutation_score"] = kernel.mutation_score(path, max_mutants=mutants)

    return {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable}
