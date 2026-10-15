"""Measure the evidence supplied by a sealed claim's checks."""

from __future__ import annotations

from . import kernel


def assess(directory, mutants=32):
    """Report measured mutation evidence and conditions that lack a measurement.

    Mutation testing is meaningful only for present, locally generated Python
    files. Other declared obligations are reported separately so a caller does
    not mistake an unmeasured property for a passing measurement.
    """
    parsed = kernel.load_recipe(directory)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity has drifted")

    measured = {}
    not_measured = {}
    not_applicable = {}

    generated = [step["output"] for step in parsed.get("step", [])
                 if step.get("kind") == "produce"
                 and step.get("class", "generated") == "generated"
                 and "from" not in step]
    python_outputs = [name for name in generated if name.endswith(".py")]
    if python_outputs and mutants > 0:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            measured["mutation"] = score
        else:
            not_measured["mutation"] = "no usable mutants"
    elif python_outputs:
        not_measured["mutation"] = "no mutants requested"
    else:
        not_applicable["mutation"] = "no locally generated Python output"

    gates = [step for step in parsed.get("step", []) if step.get("kind") == "gate"]
    if gates:
        audit = kernel.audit(directory)
        measured["gates"] = audit["gates"]
    else:
        not_applicable["gates"] = "no gate steps"

    return {"root": checked["root"], "measured": measured,
            "not_measured": not_measured, "not_applicable": not_applicable}
