"""Measure evidence supplied by a claim's gates."""

from __future__ import annotations

from . import kernel


def assess(directory: str, mutants: int = 12) -> dict:
    """Re-earn gates and, where applicable, measure generated-code mutations.

    Each bucket names evidence by its public name.  A failed or unavailable
    measurement is kept separate from a measurement that cannot apply.
    """
    if type(mutants) is not int or mutants < 0:
        raise ValueError("mutants must be a nonnegative integer")
    recipe = kernel.load_recipe(directory)
    result = {"measured": {}, "not_measured": {}, "not_applicable": {}}

    try:
        audit = kernel.audit(directory)
        result["measured"]["gates"] = audit
    except (kernel.ClaimError, OSError, ValueError) as exc:
        result["not_measured"]["gates"] = str(exc)

    generated_python = any(
        step.get("kind") == "produce" and step.get("output", "").endswith(".py")
        for step in recipe.get("step", [])
    )
    if not generated_python or mutants == 0:
        result["not_applicable"]["mutation_score"] = (
            "no generated Python" if not generated_python else "no mutants requested"
        )
    else:
        try:
            score = kernel.mutation_score(directory, max_mutants=mutants)
            if score.get("mutants", 0):
                result["measured"]["mutation_score"] = score
            else:
                result["not_applicable"]["mutation_score"] = "no available mutations"
        except (kernel.ClaimError, OSError, ValueError) as exc:
            result["not_measured"]["mutation_score"] = str(exc)
    return result
