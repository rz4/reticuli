"""Measuring how much a claim's tests prove.

A claim's gates can pass for two very different reasons: the tests
interrogate the implementation closely, or the tests simply never
exercise the paths that would catch a defect. `assess` tells the two
apart by mutation testing (`kernel.mutation_score`) and buckets every
step output the recipe declares into exactly one of three measures:

- `measured` -- a `generated` output whose every drawn mutant the gates
  killed; the tests proved this code, not merely ran alongside it.
- `not_measured` -- a `generated` output with at least one surviving
  mutant; the gates ran, but did not notice this change.
- `not_applicable` -- a `pinned`/`validated` output. It is not
  regrowable code, so mutation testing has nothing to say about it.

The three buckets partition the claim's declared outputs, so a caller
can see directly how much of what the claim is made of was actually
interrogated.
"""
from reticuli import kernel


def _output_class(step: dict) -> str:
    default = "generated" if step.get("kind") == "produce" else "pinned"
    return step.get("class", default)


def assess(d: str, *, mutants: int = 50) -> dict:
    """Bucket every declared step output of claim `d` by what its tests prove."""
    parsed = kernel.load_recipe(d)
    steps = parsed.get("step", [])

    generated, not_applicable = [], []
    for step in steps:
        output = step.get("output")
        if _output_class(step) == "generated":
            generated.append(output)
        else:
            not_applicable.append(output)

    score = kernel.mutation_score(d, max_mutants=mutants)

    survived = {label.split(":", 1)[0] for label in score["survivors"]}
    measured = [o for o in generated if o not in survived]
    not_measured = [o for o in generated if o in survived]

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "mutants": score["mutants"],
        "rate": score["rate"],
    }
