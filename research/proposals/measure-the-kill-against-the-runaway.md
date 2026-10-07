# Proposal — measure the kill against the runaway, not the limit

*Staged 2026-10-06, from closure trial 1 fourth attempt (r8). A
correction to a pin signed the previous day; a root move either way, so
the keyholder's call. Nothing here moves a root until signed.*

## The finding

Yesterday's `kill-the-whole-tree-promptly` pin replaced a too-loose
wall-clock bound (10 s for a 1 s ceiling) with a limit-shaped one
(limit × 3 + 2, so 5 s). Under the r8 trial the bound failed — and it
failed while measuring the ORIGINAL kernel, inside a nested context:
r8's audit room, inside a sandbox, running the self-claim chain build,
which itself performs rebuilds whose gates carry a 1-second ceiling.
The kill happens; the paperwork around it (process teardown,
interpreter startup, a saturated machine) crosses 5 s of wall clock.

So the criterion's verdict still depends on scheduling — the exact
defect the r7 trial reported — only now it fails under load instead of
passing under it. A tighter bound did not make the criterion decide;
it moved which way it was wrong.

## The decision this asks for

Bound the refusal against the RUNAWAY rather than the ceiling: with a
`sleep 30` gate under a 1-second limit, require the refusal to land in
under 15 seconds — less than half the time the work would have taken
if the ceiling were a lie. That is the property worth pinning (the
ceiling bounds the work, not the paperwork), it distinguishes
"killed at the limit" from "ran out" by a factor of two, and it is
robust to several seconds of load on a busy host. The grandchild probe
keeps its separate job: the kill reaches the whole process tree.

## The alternative, named honestly

Keep limit × 3 + 2 and accept that the repository cannot be audited by
a regrown judge on a loaded machine — the criterion would be measuring
the host, not the claim. Or drop the timing assertion entirely and pin
only the verdict word, which is what r7 showed to be insufficient.
The proposal recommends the runaway-relative bound.

## The lesson, for the write-up

Two signed pins in two days on the same seam, from opposite
directions: the first too loose to decide, the second too tight to
survive. The seam is real (a ceiling must bound work) and the
measurement is genuinely hard (wall clock on a shared host). Worth
recording as the clearest case the project has produced of a criterion
whose honest form took three attempts to find — and of why the
instruments, not review, are what found each miss.

## Status

Signed by the keyholder 2026-10-06 ("I sign off start the next r") and
landed the same night as one bundle with its sibling (see the
provenance record revision-2026-10-06-the-named-target-bundle.md).
