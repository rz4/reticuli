"""reticuli.assess: how much a claim's own tests prove.

Passing a claim's gates is a yes/no fact; `assess` puts a number behind
it by mutation-testing the claim's generated Python outputs
(`kernel.mutation_score`) and sorting each one into exactly one of three
buckets:

- `measured` -- the mutation engine actually drew and judged mutants of it.
- `not_measured` -- it is generated Python, but the mutant budget never
  reached it (e.g. `mutants=0`, or every mutant drawn belonged to another
  output).
- `not_applicable` -- it is not generated Python, so there is nothing to
  mutate; mutation testing cannot speak to it at all.

Stdlib only.
"""
from . import kernel


def _generated_outputs(parsed: dict) -> list:
    """Every `produce` step's output whose class is `generated`
    (the default for a produce step; see `spec/claim-format.md`)."""
    out = []
    for step in parsed.get("step", []):
        if step.get("kind") != "produce":
            continue
        if step.get("class", "generated") == "generated":
            out.append(step["output"])
    return out


def assess(d: str, *, mutants: int = None) -> dict:
    """Mutation-measure claim `d`'s generated Python outputs.

    `mutants` caps how many mutants are drawn overall, same as
    `kernel.mutation_score`'s `max_mutants`. Returns the three buckets
    above, plus the aggregate mutation result they were computed from.
    """
    parsed = kernel.load_recipe(d)
    generated = _generated_outputs(parsed)
    pythonic = [o for o in generated if o.endswith(".py")]
    not_applicable = [o for o in generated if o not in pythonic]

    score = kernel.mutation_score(d, max_mutants=mutants)

    if pythonic and score["mutants"] > 0:
        measured, not_measured = pythonic, []
    else:
        measured, not_measured = [], pythonic

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "mutants": score["mutants"],
        "rate": score["rate"],
        "survivors": score["survivors"],
    }
