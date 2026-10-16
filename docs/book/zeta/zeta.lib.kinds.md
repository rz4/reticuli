# `zeta/lib/kinds.py`

**How much a finding establishes, on a four-rung ladder.**

The queue already says what signing a finding would COST -- contraction,
eviction, repair. It did not say what the finding ESTABLISHES, and those are
independent. A contraction can be worthless (every member agrees about
something three criteria already pin) or it can be the strongest thing in the
queue (the specification has no position on the topic at all). Cost and
strength are orthogonal, and conflating them is how five redundant entries sat
at the top of a queue wearing the same label as a real gap.

The ladder, weakest first:

  FIRST KIND -- a sighting. Behaviour is unpinned and nothing came of it: no
      member is in conflict, no broken implementation would be caught. True,
      and no reason to spend a signature.

  SECOND KIND -- evidence. A trace was left: a mutant the criteria fail to
      kill. Not a hypothesis about what some implementation might do, an
      artefact on disk that does it and passes.

  THIRD KIND -- contact. Two things that both earned the root disagree. The
      equivalence class contains a contradiction right now, which is why this
      rung is the urgent one: it is not about a future implementation, it is
      about the members in hand.

  FOURTH KIND -- abduction. The specification has no position on the topic.
      Closing it adds a clause rather than a criterion, so the vocabulary
      itself grows. Only a source that reaches outside the system's own
      specification can produce one: pressure derived from the spec, or from
      mutating the implementation, can at most drive the specification toward
      being a fixpoint of itself.

A kind is assigned from what was measured, never asserted. The members decide
first, coverage can promote a sighting to evidence, and only a source that
declares a transferred silence can claim the fourth rung.

```python
from __future__ import annotations

SIGHTING = "first-kind:sighting"
EVIDENCE = "second-kind:evidence"
CONTACT = "third-kind:contact"
ABDUCTION = "fourth-kind:abduction"

LADDER = (SIGHTING, EVIDENCE, CONTACT, ABDUCTION)
RUNG = {name: index + 1 for index, name in enumerate(LADDER)}


def from_members(result):
    """The rung the member partition alone supports.

    Members in conflict is contact. Members agreeing is a sighting until
    something stronger is measured. A pressure the population could not answer
    establishes nothing and gets no rung.
    """
    if result["disposition"] == "split":
        return CONTACT
    if result["disposition"] in ("agreement", "repair"):
        return SIGHTING
    return None


def promote(current, coverage):
    """Coverage can raise a sighting to evidence; it can never lower a rung.

    A surviving mutant is a trace, which is strictly more than a sighting. It
    is strictly less than contact, because a mutant is a tree somebody built
    to be broken, while contact is two members that both earned the root.
    """
    if current == SIGHTING and coverage.get("novel"):
        return EVIDENCE
    return current


def declared(pressure):
    """A source may claim the fourth rung, and only by naming what it carried.

    `transfers` records the foreign silence whose shape was brought across --
    which population exposed it and in what. Without that provenance the claim
    is an assertion about novelty, and novelty is exactly the thing a system
    cannot assert about its own vocabulary.
    """
    carried = (pressure or {}).get("transfers")
    if carried and carried.get("from") and carried.get("silence"):
        return ABDUCTION
    return None


def assign(result, coverage=None):
    """The rung this finding reached, highest of what was actually measured."""
    reached = [k for k in (declared(result.get("pressure")),
                           from_members(result)) if k]
    if not reached:
        return None
    best = max(reached, key=lambda name: RUNG[name])
    if coverage:
        best = max([best, promote(best, coverage)], key=lambda name: RUNG[name])
    return best
```

---
*Generated from `zeta/lib/kinds.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
