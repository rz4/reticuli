"""Surface: how much a claim's own gates actually prove (spec/layers.md).

`assess` runs the mutation engine (`kernel.mutation_score`) over a claim's
generated Python and buckets what it found: `measured` is every mutant a
gate killed -- the suite tells that mutant and the real implementation
apart; `not_measured` is every survivor -- a difference the suite cannot
see; `not_applicable` is every gate whose own decider is itself generated
(`kernel.vacuous_gates`), whose verdict depends on no claimed byte, so no
mutant of a claimed byte could move it either way.
"""
from . import kernel


def assess(d: str, mutants: int = 20) -> dict:
    recipe = kernel.load_recipe(d)
    vacuous = kernel.vacuous_gates(recipe)
    score = kernel.mutation_score(d, max_mutants=mutants)
    return {
        "measured": score["killed"],
        "not_measured": len(score["survivors"]),
        "not_applicable": len(vacuous),
        "mutation": score,
        "vacuous_gates": vacuous,
    }
