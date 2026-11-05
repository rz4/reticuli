"""How much does a claim's own check actually prove?

A root names an equivalence class, and the class has a WIDTH: the set of
implementations the criteria admit. `assess` measures what it can and is
explicit about what it cannot, in three buckets, because a strength report
that quietly counts an unmeasured property as satisfied is the one failure
mode that matters here.

  * MEASURED -- this run observed it, and the number is here.
  * NOT MEASURED -- the property is live for this claim and this run did
    not establish it. Not a pass.
  * NOT APPLICABLE -- the claim declares nothing for it to be about.

The measurement leaves root-stamped residue, so the confidence ladder can
tell a claim whose tests were measured from one whose were not -- and stops
believing it the moment the root moves.
"""
import os

from . import _util
from . import kernel


def _declared(parsed: dict) -> dict:
    table = parsed.get("claim") or {}
    return {key: table[key] for key in
            ("tolerance", "envelope", "mutation_floor", "requires",
             "environment", "gate_timeout")
            if key in table}


def measurement(claim: str):
    """The last assessment of this claim, while its root still matches."""
    entry = _util.read_json(os.path.join(claim, kernel.MEASURED))
    if not isinstance(entry, dict):
        return None
    try:
        root = kernel.verify(claim)["recomputed"]
    except kernel.ClaimError:
        return None
    return entry if entry.get("root") == root else None


def assess(claim: str, mutants: int | None = None) -> dict:
    """Measure the strength of a claim's criteria."""
    parsed = kernel.load_recipe(claim)
    checked = kernel.verify(claim)
    declared = _declared(parsed)
    measured, not_measured, not_applicable = [], [], []

    if checked["ok"]:
        measured.append(f"identity holds: {checked['recomputed'][:12]}")
    else:
        not_measured.append("identity: the bytes present are a different "
                            "claim, so nothing below is about this root")

    inputs = _util.declared_inputs(parsed)
    measured.append(f"{len(inputs)} pinned input(s) decide this claim")
    vacuous = kernel.vacuous_gates(parsed)
    if vacuous:
        not_measured.append(
            f"the gate(s) {', '.join(vacuous)} are vacuous: every file "
            f"deciding them is generated")
    else:
        measured.append(f"{len(kernel.gates(parsed))} gate(s), each decided "
                        f"by at least one pinned file")

    score = None
    if mutants:
        score = kernel.mutation_score(claim, max_mutants=mutants)
        if score["rate"] is None:
            not_applicable.append(
                "mutation score: this claim's generated outputs carry no "
                "code a mutant could be drawn from")
        else:
            measured.append(
                f"mutation score: {score['rate']:.2f} over "
                f"{score['mutants']} mutant(s), "
                f"{len(score['survivors'])} survivor(s)")
    else:
        not_measured.append("mutation score: no mutants were drawn "
                            "(pass --mutants to measure it)")

    floor = declared.get("mutation_floor")
    if floor is None:
        not_applicable.append("mutation floor: this claim declares none")
    elif score and score["rate"] is not None:
        measured.append(
            f"declared mutation floor {floor}: "
            f"{'met' if score['rate'] >= floor else 'not met'}")
    else:
        not_measured.append(f"declared mutation floor {floor}: unmeasured")

    if declared.get("envelope"):
        not_measured.append(
            "the declared cost envelope: only a rebuild measures a redo's "
            "cost, and this is a measurement of the criteria")
    else:
        not_applicable.append("cost envelope: this claim declares none")
    if declared.get("tolerance") is None:
        not_applicable.append("cost band: this claim declares no tolerance")
    else:
        not_measured.append("the declared cost band: it compares two "
                            "ledgers, and this run has one claim")
    not_measured.append("producer independence: content cannot prove "
                        "blindness, so it is declared, never measured")

    result = {"name": checked["name"], "root": checked["recomputed"],
              "ok": checked["ok"],
              "measured": measured,
              "not_measured": not_measured,
              "not_applicable": not_applicable,
              "declared": declared,
              "gate": [{"output": g["output"], "run": g.get("run"),
                        "deciders": kernel.gate_deciders(g.get("run") or "")}
                       for g in kernel.gates(parsed)],
              "mutation_score": score}
    _util.write_json(os.path.join(claim, kernel.MEASURED),
                     {"root": checked["recomputed"], "when": _util.stamp(),
                      "mutation_score": score,
                      "measured": measured,
                      "not_measured": not_measured,
                      "not_applicable": not_applicable})
    return result
