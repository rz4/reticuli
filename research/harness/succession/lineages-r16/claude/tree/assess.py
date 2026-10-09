"""assess: measuring how much of a claim its own tests prove.

A gate passing once says the pinned bytes satisfy it; it says nothing about
how much of the implementation that gate actually pins down. `assess` draws
deterministic mutants from a claim's generated Python (`kernel.mutation_score`)
and sorts the result into three buckets: `measured` -- mutants the gates
caught, proof that this behavior is pinned; `not_measured` -- mutants that
survived, a gap between what the gates check and what an implementation could
get away with; `not_applicable` -- generated outputs mutation testing has
nothing to say about at all, because no gate's command even reads them
(`kernel.vacuous_gates`) or because they are not Python (`kernel.mutation_score`
only mutates `.py` sources).
"""
from reticuli import kernel


def _generated_outputs(recipe: dict) -> list:
    """Outputs of `produce` steps whose class is `generated` (the default)
    -- read straight from the parsed recipe, since no layer above the
    kernel imports a kernel private (`spec/layers.md`)."""
    return [s["output"] for s in recipe.get("step", [])
            if s.get("kind") == "produce"
            and s.get("class", "generated") == "generated"]


def assess(d: str, *, mutants: int = None) -> dict:
    """Mutation-test `d` against its own gates; bucket the result.

    `mutants` caps how many mutants `kernel.mutation_score` draws (its own
    default applies when omitted). The buckets are counts, not a verdict:
    `not_applicable` is diagnostic -- a claim with every generated output
    outside a vacuous gate's reach cannot be made to look "fully measured"
    just because nothing to mutate was offered.
    """
    recipe = kernel.load_recipe(d)
    vacuous = set(kernel.vacuous_gates(recipe))
    non_python = [o for o in _generated_outputs(recipe) if not o.endswith(".py")]

    ms = kernel.mutation_score(d, max_mutants=mutants)
    survivors = list(ms["survivors"])
    measured = ms["mutants"] - len(survivors)

    return {
        "measured": measured,
        "not_measured": len(survivors),
        "not_applicable": len(vacuous) + len(non_python),
        "mutation_score": ms,
        "survivors": survivors,
        "vacuous_gates": sorted(vacuous),
        "no_mutation_candidates": sorted(non_python),
    }
