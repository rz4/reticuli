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

# An ORACLE-BEARING pressure is classed by the verdict, not by the behaviour
# partition. A consumer substituted-into decides whether each member satisfies
# an outside standard, and the spec reserves the repair lane for exactly that:
# a standard that can say every member is wrong. This is the substitution
# finding's shape -- six rebuilds agreeing and all six breaking a consumer is
# not a free contraction click, it is a repair mandate on the whole class.
def oracle(payload, satisfied):
    return {"kind": "value", "value": {"plain": payload},
            "satisfies_oracle": satisfied}


# Every member satisfies the consumer: the obligation holds across the class,
# so pinning it evicts nobody. Contraction -- even though the members happen to
# return different values, because the oracle, not the partition, decides.
all_pass = splitlib.classify(POPULATION, PRESSURE,
                             {"one": oracle(1, True), "two": oracle(2, True),
                              "three": oracle(3, True)})
check(all_pass["disposition"] == "agreement",
      "every member satisfying the oracle is a contraction")
check(all_pass["lane"] == "contraction", "an oracle contraction evicts nobody")

# No member satisfies the consumer: the dependency's boundary is universally
# insufficient for it. A pin cannot simply be added; the class must be
# repaired. This is the 6/6-breaks case, and it must NOT read as agreement.
all_break = splitlib.classify(POPULATION, PRESSURE,
                              {"one": oracle(0, False), "two": oracle(0, False),
                               "three": oracle(0, False)})
check(all_break["disposition"] == "repair",
      "no member satisfying the oracle is a repair, never a free click")
check(all_break["lane"] == "repair", "universal oracle failure takes the repair lane")
check(splitlib.queueable(all_break), "a repair is a finding and must queue")

# The members split on the oracle: the consumer's obligation is the deciding
# criterion, and declaring it evicts the members that break it. Eviction.
# The VALUES are identical on purpose -- one behaviour class -- so the split
# can only come from the verdict. A fixture whose values differed would be a
# tautology: the ordinary len(classes)>1 branch would call it a split with the
# oracle branch deleted, and the eviction lane would go untested.
oracle_split = splitlib.classify(POPULATION, PRESSURE,
                                 {"one": oracle(0, True), "two": oracle(0, False),
                                  "three": oracle(0, False)})
check(oracle_split["disposition"] == "split",
      "members splitting on the oracle verdict is an eviction, even in one class")
check(oracle_split["lane"] == "eviction", "an oracle split takes the eviction lane")
check(oracle_split["class_count"] == 1,
      "the split is on the verdict, not the behaviour partition")
check(sorted(oracle_split["would_evict"].values()) == [1, 2],
      "eviction cost is counted over the verdict: 1 keeps, 2 break")

# An oracle verdict and a bare differential agreement are different findings:
# without the oracle bit, three members returning 0 is a contraction, and with
# it, three members FAILING the oracle with 0 is a repair. The bit decides.
bare = splitlib.classify(POPULATION, PRESSURE,
                         {name: value(0) for name in ("one", "two", "three")})
check(bare["disposition"] == "agreement",
      "the same values with no oracle bit are an ordinary contraction")
check(bare["lane"] == "contraction",
      "a differential agreement is not a repair")

# A missing bit is NOT MEASURED, never "failed the oracle". A member value or
# refusal that carries no satisfies_oracle was not put to the standard, and
# counting it as a failure manufactures a repair out of a harness fault.
# Here two members satisfy the oracle and one simply lacks the bit: the lane
# is a contraction over the two that were judged, not a split that evicts the
# unjudged one.
absent_bit = splitlib.classify(POPULATION, PRESSURE,
                               {"one": oracle(1, True), "two": oracle(1, True),
                                "three": value(1)})
check(absent_bit["disposition"] == "agreement",
      "a member with no oracle bit was not measured, not failed")
check(absent_bit["would_evict"] == {}, "a contraction evicts nobody")

# A verdict about the CLASS needs at least two members that faced the oracle.
# One member breaking a consumer while the others were never judged is a fact
# about one answer, exactly what the singleton guard forbids differentially.
one_verdict = splitlib.classify(POPULATION, PRESSURE,
                                {"one": oracle(0, False), "two": value(1),
                                 "three": value(1)})
check(one_verdict["disposition"] == "singleton",
      "a single oracle verdict cannot support a finding about the class")
check(not splitlib.queueable(one_verdict),
      "a one-verdict oracle result must not queue")

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
