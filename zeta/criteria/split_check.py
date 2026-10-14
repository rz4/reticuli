"""The classification must be decided by the population, not by the author.

These run against fixtures rather than the live queue. A criterion that read
the queue would make zeta's own verdict depend on whatever a sweep happened to
find last, and a verdict that moves on its own is not a criterion.
"""

import sys
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import probe, reduce as reducelib, split as splitlib

POPULATION = {"schema": "zeta.population.1", "name": "fixture",
              "current_root": "a" * 64,
              "members": [{"id": name, "earned_root": "a" * 64, "path": "/x",
                           "package": "p"} for name in ("one", "two", "three")],
              "retired": [], "refused": []}

PRESSURE = {"schema": "zeta.pressure.1", "source": "fixture", "id": "f/case",
            "clause": "case", "simplicity": 0, "call": "f", "args": [1],
            "specified_reader_behaviour": "n/a", "origin": "fixture"}


def value(payload):
    return {"kind": "value", "value": {"plain": payload}}


def refused(message):
    return {"kind": "refused", "error_type": "ClaimError", "error_message": message}


def check(condition, why):
    if not condition:
        raise SystemExit(f"split_check: {why}")


# Unanimity is a free click: one class, contraction lane, nobody evicted.
agree = splitlib.classify(POPULATION, PRESSURE,
                          {"one": value(1), "two": value(1), "three": value(1)})
check(agree["disposition"] == "agreement", "unanimity must be agreement")
check(agree["lane"] == "contraction", "agreement must take the contraction lane")
check(agree["would_evict"] == {}, "a contraction evicts nobody")

# Disagreement is a decision, not a tightening.
divided = splitlib.classify(POPULATION, PRESSURE,
                            {"one": value(1), "two": value(2), "three": value(2)})
check(divided["disposition"] == "split", "disagreement must be a split")
check(divided["lane"] == "eviction", "a split must take the eviction lane")
check(sorted(divided["would_evict"].values()) == [1, 2],
      "eviction cost must name what each candidate declaration would cost")

# Refusal wording is outside the equivalence: the spec requires a reason, not
# a sentence, so a criterion pinning the sentence would be author-relative.
worded = splitlib.classify(POPULATION, PRESSURE,
                           {"one": refused("no"), "two": refused("NOPE"),
                            "three": refused("not today")})
check(worded["disposition"] == "agreement",
      "members refusing with different wording still agree")
check(worded["wording_divergence"], "divergent wording must still be reported")

# A refusal and a value are never the same behaviour.
mixed = splitlib.classify(POPULATION, PRESSURE,
                          {"one": refused("no"), "two": value(1), "three": value(1)})
check(mixed["disposition"] == "split", "a refusal is not a value")

# Nothing to observe is not a finding about the specification.
dead = splitlib.classify(POPULATION, PRESSURE,
                         {name: {"kind": "unavailable", "error_type": "ImportError",
                                 "error_message": "x"} for name in ("one", "two", "three")})
check(dead["disposition"] == "invalid", "an unobservable pressure is invalid")
check(not splitlib.queueable(dead), "an invalid pressure must not queue")

# Agreement across a population of one is a fact about that implementation,
# not about the class. This is the state a root move leaves behind, so it is
# reachable in ordinary use and must not mint a free click.
alone = {"schema": "zeta.population.1", "name": "fixture",
         "current_root": "a" * 64,
         "members": [{"id": "shipped", "earned_root": "a" * 64, "path": "/x",
                      "package": "p"}], "retired": [], "refused": []}
lonely = splitlib.classify(alone, PRESSURE, {"shipped": value(1)})
check(lonely["disposition"] == "singleton",
      "one member cannot support an agreement")
check(lonely["lane"] is None, "a singleton has no lane to promote into")
check(not splitlib.queueable(lonely), "a singleton must not queue")
pair = splitlib.classify(POPULATION, PRESSURE,
                         {"one": value(1), "two": value(1)})
check(pair["disposition"] == "agreement",
      "two members agreeing is still a finding about the class")

# Controls rank, they never decide. A control outside every member class makes
# the click worth more; it cannot turn an agreement into a split.
ranked = splitlib.classify(POPULATION, PRESSURE,
                           {"one": value(1), "two": value(1), "three": value(1)},
                           {"ghost": value(99)})
check(ranked["disposition"] == "agreement", "a control cannot create a split")
check(ranked["discriminates"] == ["ghost"], "a control outside the classes ranks")
check(ranked["rank"] == 1, "rank counts discriminated controls")
inside = splitlib.classify(POPULATION, PRESSURE,
                           {"one": value(1), "two": value(1), "three": value(1)},
                           {"ghost": value(1)})
check(inside["rank"] == 0, "a control that behaves like a member ranks nothing")

# Reduction: same surface, same partition, same outcome kinds -> one finding.
def pressure(index, name):
    return {**PRESSURE, "id": f"f/{name}", "clause": name, "simplicity": index}


many = [splitlib.classify(POPULATION, pressure(i, f"c{i}"),
                          {"one": refused(f"r{i}"), "two": refused("r"),
                           "three": refused("r")})
        for i in range(4)]
collapsed = reducelib.collapse(many)
check(len(collapsed) == 1, "one phenomenon witnessed four times is one finding")
check(collapsed[0]["witness_count"] == 4, "the breadth of a phenomenon is retained")
check(collapsed[0]["pressure"]["id"] == "f/c0", "the simplest witness is kept")

# Accepting and refusing share a partition shape but are not one phenomenon.
split_kinds = reducelib.collapse([
    splitlib.classify(POPULATION, pressure(0, "accepts"),
                      {n: value(1) for n in ("one", "two", "three")}),
    splitlib.classify(POPULATION, pressure(1, "refuses"),
                      {n: refused("no") for n in ("one", "two", "three")})])
check(len(split_kinds) == 2, "unanimous acceptance and unanimous refusal differ")

# A discriminating witness outranks a simpler one, because the rank must be
# re-earnable from the bytes the entry actually retains.
chosen = reducelib.collapse([
    splitlib.classify(POPULATION, pressure(0, "plain"),
                      {n: refused("r") for n in ("one", "two", "three")}, {}),
    splitlib.classify(POPULATION, pressure(1, "sharp"),
                      {n: refused("r") for n in ("one", "two", "three")},
                      {"ghost": value(1)})])
check(len(chosen) == 1, "both witnesses describe one phenomenon")
check(chosen[0]["pressure"]["id"] == "f/sharp",
      "the retained witness must be the one the rank belongs to")

# The equivalence must ignore wording and nothing else.
check(probe.behaviour_key(refused("a")) == probe.behaviour_key(refused("b")),
      "wording must not enter the equivalence")
check(probe.behaviour_key(value(1)) != probe.behaviour_key(value(2)),
      "different values must not collapse")
check(probe.behaviour_key(refused("a")) !=
      probe.behaviour_key({"kind": "crashed", "error_type": "ClaimError",
                           "error_message": "a"}),
      "an in-band refusal is not a crash")

print("split-ok")
