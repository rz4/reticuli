"""Measure how strongly a claim's present tests constrain its build."""

from __future__ import annotations

from . import kernel


def assess(directory: str, *, mutants: int = 20) -> dict:
    """Audit a claim and report which strength measurements were possible.

    A mutation score is meaningful only for generated Python with available
    mutations.  The audit remains visible even when mutation is inapplicable.
    """
    audit = kernel.audit(directory)
    result = {
        "root": audit.get("root"),
        "ok": bool(audit.get("ok")),
        "audit": audit,
        "measured": {},
        "not_measured": {},
        "not_applicable": {},
    }
    parsed = kernel.load_recipe(directory)
    generated_python = [
        step["output"] for step in parsed.get("step", [])
        if step["kind"] == "produce"
        and step.get("class", "generated") in ("generated", "free")
        and "from" not in step and step["output"].endswith(".py")
    ]
    if not generated_python:
        result["not_applicable"]["mutation"] = "no locally generated Python"
    elif mutants <= 0:
        result["not_measured"]["mutation"] = "zero mutants requested"
    elif not audit.get("ok"):
        result["not_measured"]["mutation"] = "audit did not pass"
    else:
        score = kernel.mutation_score(directory, max_mutants=mutants)
        if score["mutants"]:
            result["measured"]["mutation"] = score
        else:
            result["not_applicable"]["mutation"] = "no applicable mutations"
    return result
