"""reticuli.assess: how much a claim's tests prove.

A gate passing says the pinned suite accepted these bytes; it does not say
how much of the generated behavior the suite actually pins down. Mutation
testing measures that: draw deterministic mutants of the generated code
(`kernel.mutation_score`) and bucket each one --

  measured       -- killed: some gate rejected the mutant, so the suite
                    proves this byte matters
  not_measured   -- survived: every gate still accepted the mutant, so the
                    suite is silent on it
  not_applicable -- no gate's verdict depends on a pinned byte at all
                    (`kernel.vacuous_gates`), so mutation has nothing to
                    measure there

Stdlib only; builds on the public kernel surface, never a kernel private.
"""
from reticuli import kernel


def assess(d, mutants=20):
    """Measure how much `d`'s pinned suite proves about its generated
    bytes. Returns the three documented buckets plus the raw mutation
    score they are drawn from."""
    parsed = kernel.load_recipe(d)
    score = kernel.mutation_score(d, max_mutants=mutants)
    vacuous = kernel.vacuous_gates(parsed)
    return {
        "measured": score["killed"],
        "not_measured": len(score["survivors"]),
        "not_applicable": len(vacuous),
        "mutants": score["mutants"],
        "rate": score["rate"],
        "survivors": score["survivors"],
        "vacuous_gates": sorted(vacuous),
    }
