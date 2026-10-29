"""Run one pressure over a population and classify what it found.

A pressure partitions the current-root members into behaviour classes. The
partition decides the lane, and the lane decides what a signature would mean:

  AGREEMENT  one class holds every current member. The behaviour is uniform
             but no criterion pins it. Declaring it evicts nobody and refuses
             future members that do otherwise: a free ratchet click.
             Lane: contraction.

  SPLIT      two or more classes. Declaring any one of them evicts the members
             in the others, so this is not a tightening -- it is a decision
             about what the software is, and it needs the louder signature.
             Lane: eviction.

  REPAIR     reserved for oracle-bearing pressures, where an outside standard
             says every member is wrong. Declaring it is a repair mandate on
             the whole population, not a pin that can simply be added.
             Differential pressure cannot produce this lane: with no oracle,
             unanimity is agreement rather than universal failure.

A pressure that no member could even attempt -- the surface is absent, or
every member died outside its own refusal path -- is INVALID and says nothing
about the specification.

DISCRIMINATION is measured, not judged. Every agreement is a free click, but
free clicks are not equally worth a signature, and the closure harness already
holds the negative controls needed to rank them: trials that failed to qualify,
and trials that qualified against a root that has since moved. A pressure that
every current member agrees on AND that a known non-qualifier answers
differently is a click that would have caught a real non-member. Controls never
decide the lane -- they are not members -- they only rank the queue.
"""

from __future__ import annotations

from . import kinds
from . import probe

SCHEMA = "zeta.split.2"
LANES = {"agreement": "contraction", "split": "eviction", "repair": "repair"}


def run(population, pressure, controls=True):
    """Observe every current-root member, then the controls, then classify."""
    observations = {m["id"]: probe.observe(m, pressure["call"], pressure["args"])
                    for m in population["members"]}
    watched = {}
    if controls:
        for member in population.get("refused", []) + population.get("retired", []):
            watched[member["id"]] = probe.observe(member, pressure["call"],
                                                  pressure["args"])
    return classify(population, pressure, observations, watched)


def classify(population, pressure, observations, controls=None):
    controls = controls or {}
    classes = {}
    for name, outcome in observations.items():
        classes.setdefault(probe.behaviour_key(outcome), []).append(name)
    for members in classes.values():
        members.sort()

    attempted = [n for n, o in observations.items()
                 if o["kind"] in ("value", "refused")]
    # An ORACLE-BEARING observation carries `satisfies_oracle`: whether that
    # member satisfied an outside standard -- a consumer whose own gate
    # re-earns, or does not, with this member substituted in. The spec reserves
    # the repair lane for exactly this: a standard outside the population that
    # can say every member is wrong. Differential pressure never carries the
    # bit, so `judged` is empty and the oracle branch is skipped entirely.
    #
    # Only a member that was actually PUT to the oracle counts. A member whose
    # observation lacks the bit was NOT MEASURED against the standard -- the
    # realization bytes were missing, the host could not test, the consumer
    # claim itself was unreadable -- and absent must read as "not measured",
    # never as "failed the oracle": reading it as failure manufactures a
    # repair out of a harness fault, which is the exact trap the probe
    # discipline exists to refuse.
    judged = {n: o["satisfies_oracle"] for n, o in observations.items()
              if o["kind"] in ("value", "refused")
              and o.get("satisfies_oracle") is not None}
    if not attempted:
        disposition, lane = "invalid", None
    elif judged:
        # A verdict about the CLASS needs at least two members that actually
        # faced the oracle -- the same reasoning as the singleton guard below,
        # counted over verdicts rather than observations. One realization
        # breaking a consumer while five others could not be observed is a
        # fact about one answer, not a repair mandate on the class.
        if len(judged) < 2:
            disposition, lane = "singleton", None
        elif not any(judged.values()):
            disposition, lane = "repair", LANES["repair"]
        elif all(judged.values()):
            disposition, lane = "agreement", LANES["agreement"]
        else:
            disposition, lane = "split", LANES["split"]
    elif len(observations) < 2:
        # Agreement across a population of one says what that implementation
        # does, which is a fact about an answer rather than about the class.
        # This is the state a root move leaves behind: every reconstruction
        # earned the old root, so until trials are re-earned the only member
        # is the authored one and no pressure can discriminate anything.
        disposition, lane = "singleton", None
    elif len(classes) == 1:
        disposition, lane = "agreement", LANES["agreement"]
    else:
        disposition, lane = "split", LANES["split"]

    # Which controls ANSWERED, and answered outside every class the members
    # occupy. Attempting is required: a control that could not run the
    # pressure at all did not survive it differently, it simply never faced
    # it, and counting that as discrimination manufactures rank. Witnessed --
    # python mutants scored 4 against a population of jq implementations,
    # every one of them merely reporting that the function did not exist.
    member_classes = set(classes)
    discriminates = sorted(name for name, outcome in controls.items()
                           if outcome["kind"] in ("value", "refused")
                           and probe.behaviour_key(outcome) not in member_classes)

    # Refusal wording is outside the equivalence on purpose. Report it anyway:
    # a criterion that pinned the sentence would be author-relative, and
    # knowing the sentences differ belongs in the record.
    wordings = sorted({o.get("error_message", "") for o in observations.values()
                       if o["kind"] == "refused" and o.get("error_message")})

    result = {"schema": SCHEMA, "population": population["name"],
            "current_root": population["current_root"],
            "pressure": pressure,
            "observations": observations,
            "controls": controls,
            "classes": {key: members for key, members in sorted(classes.items())},
            "class_count": len(classes),
            "attempted": sorted(attempted),
            "disposition": disposition, "lane": lane,
            "discriminates": discriminates,
            "rank": len(discriminates) if disposition == "agreement" else 0,
            "refusal_wordings": wordings,
            "wording_divergence": len(wordings) > 1,
            "would_evict": _eviction_cost(classes, disposition, judged)}
    # What the finding establishes, as distinct from what signing it costs.
    result["kind"] = kinds.assign(result)
    return result


def _eviction_cost(classes, disposition, judged=None):
    """For a split, how many members each candidate declaration would evict.

    Under an ORACLE split the decision is the verdict, not the behaviour
    partition, so the cost is counted over the verdict: declaring "must
    satisfy the consumer" evicts every member that did not, and declaring the
    converse evicts every member that did. Keying it by behaviour classes
    would miscount whenever two members break the consumer in different ways
    (two classes, one verdict) -- and report a zero-cost eviction when they
    break it identically.
    """
    if disposition != "split":
        return {}
    if judged:
        kept = sum(1 for v in judged.values() if v)
        broke = len(judged) - kept
        return {"satisfies-consumer": broke, "breaks-consumer": kept}
    total = sum(len(members) for members in classes.values())
    return {key: total - len(members) for key, members in sorted(classes.items())}


def queueable(result):
    """Only findings about the class queue.

    An `invalid` pressure could not be observed, and a `singleton` population
    cannot distinguish a property of the class from a property of the one
    implementation left in it. Neither is a finding, and minting either would
    fill the queue with entries a signature cannot act on.
    """
    return result["disposition"] in ("agreement", "split", "repair")
