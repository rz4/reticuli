"""Assess: how much does this claim's criteria actually prove?

A root says what a claim is, never how strongly it is held. `assess` measures
the width of the equivalence class -- which declared files the gates reach,
and which of them survive deterministic mutation -- and leaves the result as
root-stamped residue. It is a RECEIPT, not a verdict: a measurement someone
weighs, dated and named as such.
"""
import os

from . import kernel
from ._util import read_json, safe_path, write_json

#: Where a measurement is kept. Residue: outside every root.
RESIDUE = ".reticuli/assess.json"


def _reach(claim: str, parsed: dict) -> set:
    """Which declared files a gate actually reaches, one import deep."""
    from .authoring import _imported
    reached = set()
    for gate in kernel.gates(parsed):
        for decider in kernel.gate_deciders(gate.get("run") or ""):
            reached.add(decider)
            for inner in _imported(claim, decider):
                reached.add(inner)
    return reached


def assess(claim: str, mutants: int | None = None) -> dict:
    """Measure the claim's strength and leave the measurement behind."""
    checked = kernel.verify(claim)
    parsed = kernel.load_recipe(claim)
    reached = _reach(claim, parsed)
    generated = kernel.generated_outputs(parsed)
    declared = list((parsed.get("claim") or {}).get("inputs") or [])

    measured, not_measured, not_applicable = [], [], []
    score = None
    survivors = set()
    if mutants:
        score = kernel.mutation_score(claim, max_mutants=mutants)
        survivors = {label.split(":")[0] for label in score["survivors"]}

    for output in generated:
        path = safe_path(claim, output)
        if not path or not os.path.isfile(path) or not output.endswith(".py"):
            not_applicable.append(output)
            continue
        if score is None:
            not_measured.append(output)
        elif output in survivors:
            not_measured.append(output)
        else:
            measured.append(output)

    table = parsed.get("claim") or {}
    report = {
        "name": checked["name"], "root": checked["recomputed"],
        "ok": checked["ok"],
        "measured": sorted(measured),
        "not_measured": sorted(not_measured),
        "not_applicable": sorted(not_applicable),
        "declared": sorted(declared),
        "reached": sorted(reached),
        "gate": [g.get("run") for g in kernel.gates(parsed)],
        "vacuous": kernel.vacuous_gates(parsed),
        "mutation_score": score,
        "mutation_floor": table.get("mutation_floor"),
        "when": kernel._now(),
    }
    write_json(os.path.join(claim, RESIDUE), report)
    return report


def recorded(claim: str) -> dict | None:
    """A measurement left here earlier -- only while the root still matches.

    A receipt whose root has moved is a receipt about a different claim, so it
    is dropped rather than shown beside bytes it never measured.
    """
    report = read_json(os.path.join(claim, RESIDUE))
    if not isinstance(report, dict):
        return None
    try:
        checked = kernel.verify(claim)
    except kernel.ClaimError:
        return None
    if report.get("root") != checked["recomputed"]:
        return None
    return report
