"""Measuring how much a claim's tests prove (`spec/layers.md`: surface).

A gate's pinned bytes say a claim passed; they say nothing about how much of
the generated code that pass actually exercises. `assess` answers that with
deterministic mutation testing (`kernel.mutation_score`): each mutant sorts
into one of three buckets --

- `measured`   -- the gate caught the mutant (something the tests proved);
- `not_measured` -- the gate missed the mutant (generated behavior the tests
  never exercise);
- `not_applicable` -- a gate whose every decider is itself generated code
  (`kernel.vacuous_gates`) can't measure anything at all; no mutant was ever
  run against it.

Only the public kernel surface (`reticuli.kernel`) is used, per
`spec/layers.md`. Stdlib only.
"""
from reticuli import kernel


def assess(d: str, mutants: int = None) -> dict:
    """Measure `d`'s mutation coverage; buckets per the module docstring."""
    parsed = kernel.load_recipe(d)
    vacuous = sorted(kernel.vacuous_gates(parsed))
    score = kernel.mutation_score(d, max_mutants=mutants)
    survivors = score["survivors"]
    total = score["mutants"]
    killed = total - len(survivors)
    return {
        "measured": killed,
        "not_measured": len(survivors),
        "not_applicable": len(vacuous),
        "mutants": total,
        "rate": score["rate"],
        "survivors": survivors,
        "vacuous_gates": vacuous,
    }
