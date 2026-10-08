"""Measuring a claim's strength, not merely whether its gates pass
(spec/layers.md's surface layer).

`assess` spends a mutation-testing budget (`kernel.mutation_score`) and
buckets it into what the tests actually proved: a mutant drawn and killed
is `measured`; a mutant drawn and surviving is `not_measured` -- the tests
let that behavior through; and budget the mutation engine never had a
distinct mutant to spend -- fewer candidates than the requested budget --
is `not_applicable`, never counted as either a pass or a gap.
"""
from . import kernel


def assess(d: str, mutants: int = 50) -> dict:
    """How much of `d`'s generated code the claim's own tests prove, out of
    a `mutants`-sized budget."""
    result = kernel.mutation_score(d, max_mutants=mutants)
    drawn = result["mutants"]
    survived = len(result["survivors"])
    killed = drawn - survived
    return {
        "mutants": drawn,
        "rate": result["rate"],
        "measured": killed,
        "not_measured": survived,
        "not_applicable": max(0, mutants - drawn),
    }
