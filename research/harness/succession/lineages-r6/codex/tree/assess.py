"""Measure how strongly a claim's gates constrain its generated code."""
from __future__ import annotations

from typing import Any

from . import kernel


def assess(directory: str, mutants: int = 20) -> dict[str, Any]:
    """Return mutation evidence in measured, unmeasured, and inapplicable buckets.

    A baseline audit is needed before a mutation score says anything useful.
    Claims without generated Python files have no supported mutation targets.
    """
    parsed = kernel.load_recipe(directory)
    checked = kernel.verify(directory)
    if not checked["ok"]:
        return {"measured": {}, "not_measured": {"mutation": "identity mismatch"},
                "not_applicable": {}, "ok": False}
    audit = kernel.audit(directory)
    if not audit.get("ok"):
        return {"measured": {"audit": audit},
                "not_measured": {"mutation": "baseline gates did not pass"},
                "not_applicable": {}, "ok": False}
    outputs = [name for name in kernel.generated_outputs(parsed) if name.endswith(".py")]
    if not outputs:
        return {"measured": {"audit": audit}, "not_measured": {},
                "not_applicable": {"mutation": "no generated Python output"}, "ok": True}
    if mutants <= 0:
        return {"measured": {"audit": audit},
                "not_measured": {"mutation": "mutant limit is zero"},
                "not_applicable": {}, "ok": True}
    score = kernel.mutation_score(directory, max_mutants=mutants)
    if score["mutants"] == 0:
        return {"measured": {"audit": audit}, "not_measured": {},
                "not_applicable": {"mutation": "no supported mutations"}, "ok": True}
    return {"measured": {"audit": audit, "mutation": score},
            "not_measured": {}, "not_applicable": {}, "ok": True}
