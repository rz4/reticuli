"""A rung is assigned from what was measured, never asserted.

The ladder says how much a finding establishes, and the whole point is that a
finding cannot award itself a rung. Three ways that could go wrong:

A rung could be CLAIMED. The fourth kind means the specification has no
position on a topic, and no system can assert that about its own vocabulary --
the claim is only as good as the foreign silence it carried across, so it must
name one.

A rung could be INFLATED. A mutant somebody built to be broken is weaker
evidence than two members that both earned the root, so coverage may raise a
sighting to evidence and must never reach contact.

A rung could be LOST. Contact is the urgent rung, because the contradiction is
between members in hand rather than hypothetical. Nothing may demote it.
"""

import sys
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import coverage as coveragelib, kinds, split as splitlib

ROOT = "a" * 64
POPULATION = {"schema": "zeta.population.1", "name": "fixture",
              "current_root": ROOT,
              "members": [{"id": name, "earned_root": ROOT, "path": "/x",
                           "package": "p"} for name in ("one", "two")],
              "retired": [], "refused": []}
PRESSURE = {"schema": "zeta.pressure.1", "source": "fixture", "id": "f/case",
            "clause": "case", "simplicity": 0, "call": "f", "args": [1],
            "specified_reader_behaviour": "n/a", "origin": "fixture"}


def check(condition, why):
    if not condition:
        raise SystemExit(f"kind_check: {why}")


def value(payload):
    return {"kind": "value", "value": {"plain": payload}}


def report(surviving):
    return {"schema": "zeta.coverage.1", "criteria_digest": "d" * 64,
            "baseline": {"control": "baseline", "killed": False},
            "killed": ["mutant:killed"], "surviving": list(surviving),
            "contradictions": [], "rows": []}


# The ladder is ordered, and the order is the whole content of the thing.
check(kinds.LADDER == (kinds.SIGHTING, kinds.EVIDENCE, kinds.CONTACT,
                       kinds.ABDUCTION), "the ladder is weakest first")
check([kinds.RUNG[k] for k in kinds.LADDER] == [1, 2, 3, 4],
      "each rung is numbered by its position")

# Members agreeing is a sighting; members in conflict is contact.
agreed = splitlib.classify(POPULATION, PRESSURE,
                           {"one": value(1), "two": value(1)})
check(agreed["kind"] == kinds.SIGHTING, "agreement alone is a sighting")
divided = splitlib.classify(POPULATION, PRESSURE,
                            {"one": value(1), "two": value(2)})
check(divided["kind"] == kinds.CONTACT, "members in conflict is contact")

# A pressure the population could not answer establishes nothing.
dead = splitlib.classify(POPULATION, PRESSURE,
                         {n: {"kind": "unavailable", "error_type": "E",
                              "error_message": "x"} for n in ("one", "two")})
check(dead["kind"] is None, "an unobservable pressure reaches no rung")
alone = splitlib.classify({**POPULATION, "members": POPULATION["members"][:1]},
                          PRESSURE, {"one": value(1)})
check(alone["kind"] is None, "a singleton population reaches no rung")

# A surviving mutant is a trace, so it raises a sighting to evidence.
raised = coveragelib.annotate(agreed, report(["mutant:c"]))
check(raised["kind"] == kinds.SIGHTING,
      "a sighting that separates no survivor stays a sighting")
ranked = dict(agreed, rank=1, discriminates=["mutant:c"])
raised = coveragelib.annotate(ranked, report(["mutant:c"]))
check(raised["kind"] == kinds.EVIDENCE, "separating a survivor is evidence")

# A killed mutant is not a trace: the criteria already catch that.
stays = coveragelib.annotate(dict(agreed, rank=1,
                                  discriminates=["mutant:killed"]),
                             report(["mutant:c"]))
check(stays["kind"] == kinds.SIGHTING,
      "separating only killed mutants leaves a sighting a sighting")

# Coverage must never reach contact, and must never demote it.
check(kinds.promote(kinds.EVIDENCE, {"novel": True}) == kinds.EVIDENCE,
      "coverage cannot raise evidence to contact")
held = coveragelib.annotate(dict(divided, rank=1, discriminates=["mutant:c"]),
                            report(["mutant:c"]))
check(held["kind"] == kinds.CONTACT, "contact is never demoted by coverage")
for rung in kinds.LADDER:
    check(kinds.RUNG[kinds.promote(rung, {"novel": True})] >= kinds.RUNG[rung],
          f"promotion never lowers {rung}")

# The fourth kind must be earned by naming the foreign silence it carried.
# A system cannot assert novelty about its own vocabulary.
check(kinds.declared({}) is None, "no provenance, no fourth rung")
check(kinds.declared({"transfers": {}}) is None, "an empty transfer claims nothing")
check(kinds.declared({"transfers": {"from": "jq"}}) is None,
      "a source without a named silence claims nothing")
check(kinds.declared({"transfers": {"silence": "number form"}}) is None,
      "a silence without a named population claims nothing")
check(kinds.declared({"transfers": {"from": "jq", "silence": "number form"}})
      == kinds.ABDUCTION, "provenance on both sides earns the fourth rung")

# And a transferred pressure outranks what the members alone would support.
carried = {**PRESSURE, "transfers": {"from": "jq", "silence": "number form"}}
lifted = splitlib.classify(POPULATION, carried,
                           {"one": value(1), "two": value(1)})
check(lifted["kind"] == kinds.ABDUCTION,
      "a named transfer reaches the fourth rung over a sighting")

print("kind-ok")
