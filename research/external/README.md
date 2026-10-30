# External targets: the stack pointed at software nobody here wrote

Reticuli names a boundary; zeta measures what the boundary leaves open. The
honest test of both is a target the project did not design around. This
directory holds those targets, each one an independent spec with two or more
implementations written by people who were not coordinating, so a divergence
between them is negative space in a boundary someone else owns — grade 2 by
differential pressure, no producer required.

| target | implementations | what it showed |
|---|---|---|
| [`jq/`](jq/) | jq, gojq, jaq (three) | the original external arm: a quarter of jq's own test corpus is undecided between its implementations; a blind rebuild that passed 465/465 was a lookup table; a signed repair measurably contracted the spec's silence. The deep, producer-driven arm. |
| [`sed/`](sed/) | BSD `sed`, GNU `gsed` | first target the instrument was *not* built for. 14/26 probed corners agree; `a\` append diverges on the trailing newline (on the POSIX form both accept); `\+ \? \|` are literals vs operators *silently*. `findings.md`. |
| [`tr/`](tr/) | BSD `tr`, GNU `gtr` | a target of a different *shape* — spec as set-arguments, no stdin program. 13/14 agree; they part only on a descending range (`c-a`), which BSD reverses and GNU refuses. |

## What this collection establishes

The same classifier — zeta's `split`, the one the closure work hardened —
produced reproducible negative-space maps for three independent tools, two of
them met after the instrument was already built, one of them a different
invocation shape entirely (tr gathers its own observations and still classifies
through zeta). That is the "point zeta at any git repository" claim reduced to
what is demonstrable today: the **measurement half** generalises.

The contrast across targets is itself a reading. sed, a small language, splits
on nearly half its probed corners; tr, a simpler filter, on one in fourteen.
Determinacy is a property of the spec, and differential pressure measures it
directly — the tighter the agreement between independent implementations, the
less silence the spec left.

## What it does not establish

Every target here is the **measurement half** of the reconstruct-codebase
loop: differential probing of implementations that already exist. None carries
a blind rebuild to replacement-grade, because that needs a model producer and a
frozen corpus — the jq arm is the only one that went there, and it stalled at
`S_2` on 2026-10-11 with its elections unsigned. The sed and tr probe sets are
hand-picked at known-divergent corners, so their agreement rates are sample
properties, not coverage. And a two-implementation split is a lower bound on a
spec's negative space (the aperture argument); a third implementation widens
it, which is why jq used three and why busybox/toybox sed would sharpen sed if
they were on hand.

Which side of any divergence is *correct* is never decided here. That is an
election — the keyholder's, not the instrument's.
