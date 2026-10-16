# Zeta internals

Zeta is the exploratory instrument: it measures where a specification is
silent by probing populations of implementations that all pass the current
gate, and it stages what it finds for human review. This page is the map
over its machinery; [the woven modules](book/index.md) are the machinery
itself. Zeta holds no authority anywhere — the primary claim's own pinned
criteria forbid depending on it — and everything below is designed around
that fact.

## Populations: who gets probed

A population is a set of implementations whose members all earned the
current root, plus labeled non-members used as controls:

- **reconstructions** — independently regrown implementations, the core
  population;
- **deployment** — the same authored bytes under each host environment the
  claim declares it supports, so a split here is host dependence the root
  does not pin;
- **a foreign control** — several independent implementations of a
  specification *written by somebody else* (here, the jq language). In the
  home population, criteria and candidates share an author lineage, so a
  tight class may be tight partly because of that; the foreign family is
  the control for exactly this contamination.

Membership is relative to a root. When the root moves, members earned
against the old one are retired, not evicted retroactively — they remain
true records of what was seen then, and stop being arguments about now.
Rejected and retired implementations are kept and probed as controls: a
defect a real producer actually made ranks a probe's usefulness better
than a defect anyone imagined.

## Probes and splits: the measurement

A probe puts one call to every member in a subprocess and records an
outcome: a value, a refusal, or a crash. Outcomes are compared by a
behavior key that deliberately ignores differences the specification
licenses (refusal *wording*, for instance — the spec requires a reason,
not a sentence). A probe that partitions the population has found behavior
the root does not determine. Many probes typically expose one underlying
difference, so findings are reduced to phenomena — one witness per
distinct partition-and-outcome signature — before anything is stored.

## Lanes: what adopting a finding would cost

Every finding is classified by the price of pinning it:

- **contraction** — all members already agree; writing the behavior down
  evicts no one. Cheap to adopt, and the most common.
- **eviction** — members disagree; pinning either side excludes a standing
  implementation. Adoption is a genuine decision.
- **repair** — an independent oracle says every member is wrong; the
  specification itself has a defect.

## The ladder: what a finding has established

Orthogonal to lanes, a finding's evidential strength:

1. **sighting** — a probe answered differently than expected, once;
2. **evidence** — the criteria demonstrably cannot see the behavior (a
   deliberately broken variant survives them);
3. **contact** — members in verified conflict;
4. **transfer** — the specification has no position at all, and the gap
   was found by carrying a silence in *from outside* — with the source
   population and the silence both named, because no system can assert
   novelty about its own vocabulary.

The lane says what adopting would cost; the rung says whether there is
anything to adopt. Review time goes first to high-rung findings whatever
their lane.

## Coverage: is a finding new, and does the harness still see?

Before a finding is worth review, two questions are answered mechanically.
A battery of deliberately broken implementations — each breaking one named
thing, with a declared expectation — runs against the criteria. A mutant
the criteria kill means that pressure was redundant: the root already pins
it. A surviving mutant is a criterion gap. And one mutant is *expected to
survive* (a licensed difference the criteria should not care about): if it
is ever killed, or if a baseline unmutated run fails, the battery refuses
to report at all, because its kills would be artifacts.

## Entries: findings that replay anywhere

A queued finding is packaged as its own small claim: the probe, the
observed partition, the population it was observed against, and **the
classifier code that judged it**, all together, re-runnable cold with no
reference to zeta, its author, or the machine of origin. This is the
property that makes the instrument extensible to untrusted sources —
including agent-generated probes: nothing about a finding's origin
survives into the evidence, so the origin never needs to be trusted.
Entries observed against a retired root are marked stale and sort last;
they are records, not arguments.

## Selection: comparing members without electing one

One more instrument, deliberately powerless: members of the current class
are measured on axes declared in advance — total size, code size, audit
time, and *documentation mass, where more is better*. The result is a
Pareto frontier, never a winner: a non-member can never appear on it
(otherwise the empty program wins every size axis), and no ranking is
offered, because collapsing the axes would quietly recommend trading away
the one quantity — explanatory prose — that keeps a generated tree
maintainable by people. Moving between members changes no identity and
needs no signature; recommending one is left to humans, on the record.

## The boundary, restated

Everything above may be wrong at agent speed: probes mistaken, agents
sloppy, classifications revised. The design absorbs this because zeta's
output is *candidates*, every candidate replays independently, and the
only path from candidate to obligation is a
[human signature](process.md#6-evolve-the-outer-loop-where-obligations-change).
The instrument is allowed to be fast because it is not allowed to decide.
