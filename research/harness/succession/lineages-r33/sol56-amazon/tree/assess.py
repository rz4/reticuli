"""Measure the strength of a claim's acceptance checks.

Assessment is diagnostic rather than identity-bearing.  Every observation is
placed in one of three explicit buckets: measured, not measured, or not
applicable.  In particular a missing measurement is never presented as zero.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from . import kernel


def _generated(recipe: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for step in recipe.get("step", []):
        if (isinstance(step, Mapping) and step.get("kind") == "produce"
                and step.get("class", "generated") in ("generated", "free")
                and "from" not in step and isinstance(step.get("output"), str)):
            result.append(step["output"])
    return result


def assess(d: str | os.PathLike[str], mutants: int = 100, **options: Any) -> dict[str, Any]:
    """Assess how much the tests in claim *d* presently demonstrate.

    ``mutants`` bounds deterministic mutation work.  Mutation is applicable
    only when the claim has a present, textual generated implementation.  A
    failed identity check is reported as not measured rather than accidentally
    testing bytes that no longer belong to the sealed claim.
    """
    directory = os.path.abspath(os.fspath(d))
    measured: dict[str, Any] = {}
    not_measured: dict[str, Any] = {}
    not_applicable: dict[str, Any] = {}

    try:
        recipe = kernel.load_recipe(directory)
        verification = kernel.verify(directory)
    except kernel.ClaimError as exc:
        not_measured["identity"] = str(exc)
        return {"measured": measured, "not_measured": not_measured,
                "not_applicable": not_applicable, "ok": False}

    measured["identity"] = {
        "ok": bool(verification.get("ok")),
        "root": verification.get("root"),
    }
    gates = [step for step in recipe.get("step", [])
             if isinstance(step, Mapping) and step.get("kind") == "gate"]
    measured["gates"] = {"declared": len(gates)}

    generated = _generated(recipe)
    textual = []
    for name in generated:
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as stream:
                stream.read()
            textual.append(name)
        except (OSError, UnicodeError):
            pass

    if not verification.get("ok"):
        not_measured["mutation"] = "claim identity does not hold"
    elif mutants is None or isinstance(mutants, bool) or not isinstance(mutants, int) or mutants < 0:
        not_measured["mutation"] = "mutants must be a non-negative integer"
    elif not generated:
        not_applicable["mutation"] = "claim has no generated outputs"
    elif not textual:
        not_applicable["mutation"] = "claim has no present textual generated outputs"
    elif mutants == 0:
        not_measured["mutation"] = "mutation budget is zero"
    else:
        try:
            score = kernel.mutation_score(directory, max_mutants=mutants)
            measured["mutation"] = score
        except kernel.ClaimError as exc:
            not_measured["mutation"] = str(exc)

    # Held-out evaluation needs an independently supplied check.  Its absence
    # is an honest unmeasured bucket, not a weakness score of zero.
    if options.get("heldout") is None:
        not_measured["heldout"] = "no held-out check supplied"

    return {
        "measured": measured,
        "not_measured": not_measured,
        "not_applicable": not_applicable,
        "ok": bool(verification.get("ok")),
    }


__all__ = ["assess"]
