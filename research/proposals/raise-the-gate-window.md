# Proposal — the gate window admits the class, not the author's pace

*Staged 2026-10-06, from closure trial 1 third attempt (r7). A
contract decision for the keyholder; the declared `gate_timeout` sits
in the recipe, inside the root, so this is a root move needing the
signature either way it goes.*

## The finding

The r7 tree failed the substituted full gate at 1800.019 seconds — the
declared ceiling to the millisecond — with every criterion it reached
passing and the whole bootstrap holding. The first generation refused
by cost alone. The r2 record predicted this would be the last wall;
it is. Measured: the chain build alone runs ~16 minutes under the r7
implementation against ~10 under the original — a conforming member
roughly 1.6× slower, and the 30-minute window was calibrated to the
original's pace.

## The decision this asks for

Raise `gate_timeout` to 3600. The doctrine already says "behavior is
pinned, speed is not, beyond the declared window" — but a window
calibrated to the author's own implementation quietly makes membership
author-relative and host-relative, which is exactly what the class is
not supposed to be. 3600 admits implementations up to ~3× the
original's pace on this host, which covers every conforming tree
sampled to date. The audit-diet work (incremental self_check through
the shipped reuse primitive) remains the real fix and can land later
as ordinary engineering; the window buys the closure arc the room to
measure what it set out to measure — specification completeness, not
interpreter pace.

## The alternative, named honestly

Keep 1800 and make pace part of the claim: a member too slow to
self-audit in the window is not a member. Coherent — cost envelopes
are real criteria here — but it means the closure bar measures
producer code style as much as boundary completeness, and the k=3
count waits on model codegen speed. If chosen, the honest companion is
publishing the pace requirement as an explicit criterion rather than a
calibration accident.

## Status

Signed by the keyholder 2026-10-06 ("I sign off on them, start working
on r8") and landed the same day as one bundle with its sibling (see the
provenance record revision-2026-10-06-format-4-and-the-hour.md).
