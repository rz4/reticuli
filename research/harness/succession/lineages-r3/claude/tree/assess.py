"""Assessing how much a claim's tests prove (surface layer).

A mutation-killed survivor is a gap: the pinned gates passed on code that
differs from what was realized, so whatever that mutant changed is not
actually proven by the suite. `assess` buckets the claim's generated-Python
surface three ways, read rather than judged:

- `measured`   -- mutants the gates caught; the suite demonstrably proves
                  the behavior those mutants changed.
- `not_measured` -- mutants that survived; the suite says nothing about
                  the behavior those mutants changed.
- `not_applicable` -- generated outputs mutation testing cannot address at
                  all: not Python, or declared but not present on disk.

This is a read of what `kernel.mutation_score` already measured, plus the
part of the claim's declared surface that mutation never touches; it adds
no gate of its own and never changes the claim's identity.
"""
import os

from . import kernel


def assess(d: str, mutants: int = None) -> dict:
    """Measure how much of `d`'s generated Python the gates actually prove.

    `mutants` caps how many mutants are tried (kernel.mutation_score's
    `max_mutants`); omit it to use the kernel's own default.
    """
    if mutants is None:
        score = kernel.mutation_score(d)
    else:
        score = kernel.mutation_score(d, max_mutants=mutants)

    survivors = score.get("survivors", [])
    total = int(score.get("mutants", 0))
    not_measured = len(survivors)
    measured = max(total - not_measured, 0)

    parsed = kernel.load_recipe(d)
    not_applicable = 0
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") != "generated":
            continue
        output = step.get("output", "")
        if not output.endswith(".py") or not os.path.isfile(os.path.join(d, output)):
            not_applicable += 1

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "mutants": total,
        "rate": score.get("rate"),
        "survivors": survivors,
    }
