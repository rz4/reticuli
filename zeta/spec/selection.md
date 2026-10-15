# Selection

Everything else here contracts. Pressure finds unpinned surface, a signature
declares it, the class gets smaller and reconstruction gets harder. The lanes
are all narrowings — contraction, eviction, repair — and none of them can say
*here is a better member*, because that is not a statement about the
specification at all.

Selection is the other direction, and it costs almost nothing.

## Why it is free

The root excludes the implementation by construction. `verify` compares only
the root — "a generated rebuild keeps them equal" — and membership is decided
by the gate. So moving from one member to another:

| | contraction | selection |
|---|---|---|
| root moves | every time | never |
| signature | required; no agent signs | none needed |
| population | retired, hours to rebuild | untouched |
| reconstruction | harder | unchanged |

That asymmetry is the whole reason this lane exists. On 2026-10-14 three root
moves were spent sharpening the boundary, each retiring the entire
reconstruction population, while the first genuine improvement the project had
ever found — a reconstruction 2.5× smaller and 13% faster than the shipped
tree, earning the same gate — sat unremarked in a trial's output, costing
nothing.

## Membership first

A candidate that does not earn the claim's gate is not a cheaper member; it is
not a member. A frontier that admitted non-members would rank programs rather
than answers, and the smallest program is always the one that does nothing.

This is not hypothetical. Under an instruction to minimise, a producer in this
project collapsed to the blind prior in a single step. **Tight criteria are
what make a small member trustworthy**, which is why contraction is the
precondition for selection rather than its rival: zeta's entire contracting
output is what makes this lane safe to run at all.

The same reasoning says where candidates may come from. A reconstruction is a
safe candidate because it was produced **blind** — the producer never saw size
or speed as a goal, so a smaller member is a side effect of independent
authorship rather than an optimisation target. Point a producer at the fitness
function and that safety is gone.

## Axes declared before measuring

A fitness chosen once the winner is known is a story about the winner. The
axes are fixed in source, each naming what it measures and why nothing in the
root constrains it — an axis the root pins is a criterion, not a preference —
and the declaration's digest travels with every result, so a later addition is
visible rather than silent.

## No winner, ever

One axis runs against the others on purpose. `prose_bytes` counts comments and
docstrings, and **more is better**, because that is the institutional memory:
the dated witnesses, the reason each guard exists, the record of what failed
before. A reconstruction carries almost none of it — measured at 8% of the
authored prose — because the boundary transmits behaviour and never reasoning.

So a reconstruction is smaller partly by being better and partly by being
amnesiac, and no gate can tell those apart. Collapsing the axes into a single
ranking would need weights trading maintainability against size, and nothing
measures maintainability. Selection therefore reports the **frontier** — every
member no other member beats on all axes at once — and a person chooses.

The first real survey found both members on the frontier, which is the correct
answer: the reconstruction wins on size, code and audit cost, the authored tree
wins on prose by thirteen times, and neither dominates.
