"""Measuring how much a claim's criteria actually prove.

A root names an equivalence class, and the honest question about a claim is
how WIDE that class is.  `assess` answers it in three buckets rather than one
number, because the three mean different things to a reader:

* **measured** — a generated file the criteria reach, with mutants they kill;
* **not_measured** — a generated file no criterion reaches, or one whose
  mutants all survive: the claim says nothing about it;
* **not_applicable** — a file with no mutable behaviour to measure.

The result is left as root-stamped residue, so a later view can report it
only while the root still matches: a measurement of a claim that has since
moved is a measurement of something else.  It is a receipt, not a verdict.
"""
import os

from . import _util, authoring, kernel


def assess(claimdir: str, mutants: int = None) -> dict:
    """Measure the specification's strength, and leave the measurement behind."""
    parsed = kernel.load_recipe(claimdir)
    checked = kernel.verify(claimdir)
    declared = {key: parsed["claim"][key]
                for key in ("tolerance", "envelope", "mutation_floor",
                            "requires", "environment")
                if key in parsed["claim"]}
    gates = [gate["output"] for gate in kernel.gates(parsed)]

    reached = set()
    for gate in kernel.gates(parsed):
        for decider in kernel.gate_deciders(gate.get("run") or ""):
            reached.add(decider)
            reached.update(authoring._imports(claimdir, decider))
        for token in authoring._tokens(gate.get("run") or ""):
            if authoring._entry(claimdir, token):
                reached.add(token)

    score = None
    if mutants:
        score = kernel.mutation_score(claimdir, max_mutants=mutants)
    survived = set()
    for label in (score or {}).get("survivors", []):
        survived.add(label.split("@")[0])

    measured, not_measured, not_applicable = [], [], []
    for name in kernel.generated_outputs(parsed):
        if not name.endswith(".py"):
            # Nothing here can mutate a non-Python output in a way a gate
            # could notice, so reporting it as unmeasured would be a false
            # alarm rather than a finding.
            (measured if name in reached else not_applicable).append(name)
            continue
        if name not in reached:
            not_measured.append(name)
        elif score is not None and name in survived \
                and score["rate"] == 0.0:
            not_measured.append(name)
        else:
            measured.append(name)

    result = {
        "name": checked["name"], "root": checked["recomputed"],
        "ok": checked["ok"],
        "measured": measured, "not_measured": not_measured,
        "not_applicable": not_applicable,
        "declared": declared, "gate": gates,
        "mutation_score": score, "when": _util.stamp(),
        "host": kernel._judging_host(),
    }
    # Root-stamped residue: a measurement belongs to the claim it measured.
    _util.write_json(os.path.join(claimdir, kernel.DECIDING), result)
    return result
