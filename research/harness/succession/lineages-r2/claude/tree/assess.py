"""assess: how much a claim's tests actually prove (spec/verification.md).

A gate passing says the pinned bytes satisfy it; it says nothing about
whether the gate would have caught a *wrong* implementation. Mutation
testing is the kernel's own instrument for that (`kernel.mutation_score`):
deterministic mutants of the generated Python, drawn from the root, and the
share of them a claim's gates still kill.

`assess` reads that instrument gate by gate rather than claim-wide, and
buckets every gate into exactly one of three groups:

- `measured`    -- the gate is not vacuous (`kernel.vacuous_gates`: at least
                   one of its deciders is a pinned file, not only generated
                   ones) and this run drew at least one mutant to test it
                   against.
- `not_measured` -- the gate is not vacuous, but no mutant was drawn for it
                   this run (an empty or exhausted mutation budget); wider
                   sampling might still measure it.
- `not_applicable` -- the gate is vacuous: every file that decides it is a
                   generated output, so no byte a mutation could touch is
                   pinned against it, and mutation testing has nothing to
                   say about it (spec/claim-format.md's own name for this
                   gap, "vacuous gates refused" at seal time not
                   withstanding -- a still-vacuous gate on an already-sealed
                   claim is exactly what this bucket is for).

Stdlib only.
"""
from . import kernel


def assess(d: str, mutants: int = 20) -> dict:
    """Bucket every gate step of claim `d` into `measured`, `not_measured`,
    or `not_applicable`, using at most `mutants` deterministic mutants."""
    parsed = kernel.load_recipe(d)
    vacuous = set(kernel.vacuous_gates(parsed))
    gate_steps = [s for s in parsed.get("step", []) if s["kind"] == "gate"]

    if mutants and mutants > 0:
        score = kernel.mutation_score(d, max_mutants=mutants)
    else:
        score = {"mutants": 0, "killed": 0, "rate": 0.0, "survivors": []}

    measured, not_measured, not_applicable = [], [], []
    for step in gate_steps:
        output = step["output"]
        if output in vacuous:
            not_applicable.append(output)
        elif score["mutants"] > 0:
            measured.append(output)
        else:
            not_measured.append(output)

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "mutation_score": score,
    }
