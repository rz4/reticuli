"""Assess: how much a claim's own tests prove.

A gate passing says only that the bytes present satisfy it; it says
nothing about whether the gate would notice if those bytes were wrong.
`assess` answers that by mutation-testing a claim's generated Python
outputs (`kernel.mutation_score`) and sorting every generated output into
one of three buckets:

- `measured`   -- mutants of this output were drawn and at least one was
                  killed: some test the claim pins actually depends on
                  this file's behavior.
- `not_measured` -- generated Python, but no mutant drawn from it was
                  killed (zero mutants, or every one survived): the
                  claim's own gates do not visibly constrain this file.
- `not_applicable` -- not Python, or not generated at all: mutation
                  testing (as this kernel implements it) does not reach
                  it; reaching no verdict is honest, not a failure.

Nothing here is identity-bearing or touches the root; it reads a sealed
claim and reports residue about its own test suite.

Stdlib only.
"""
import os

from . import kernel


def _generated_outputs(recipe: dict) -> list:
    outputs = []
    for step in recipe.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") != "generated":
            continue
        outputs.append(step["output"])
    return outputs


def assess(d: str, mutants: int = None) -> dict:
    """Bucket a sealed claim's generated outputs by how much mutation
    testing shows its gates actually prove about them."""
    d = os.path.abspath(d)
    recipe = kernel.load_recipe(d)
    generated = _generated_outputs(recipe)

    not_applicable = [o for o in generated if not o.endswith(".py")]
    pyfiles = [o for o in generated if o.endswith(".py")]

    measured = []
    not_measured = []
    mutation = None
    if pyfiles:
        mutation = kernel.mutation_score(d, mutants)
        if mutation["killed"] > 0:
            measured = list(pyfiles)
        else:
            not_measured = list(pyfiles)

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "mutation": mutation,
    }
