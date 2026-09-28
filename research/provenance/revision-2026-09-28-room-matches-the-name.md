# Revision: the room matches the name, and the record carries the terms

The repository claim moved on 2026-09-28, `5b8be784…` → `16297fb0…`. One
transition, three coordinated boundary edits, all descending from the
cross-family reading of 2026-09-22
([`research/audits/2026-09-22-cross-family-essence-and-soundness.md`](../audits/2026-09-22-cross-family-essence-and-soundness.md)):
the reading's essence statement — the root is exactly what decides
acceptance, purified of everything that cannot — and its three verified
places where the code fell short of that.

## What moved, and why the root moved with it

**Finding A — the room now matches the name.** `spec/identity.md` asserted
that a byte of guidance cannot change whether any realization passes. The
counterexample in `research/audits/finding-a-repro/` disproved that as
implemented: the judging room received the raw recipe, so a format-3 gate
that read its own guidance could accept differently for the same root. The
kernel now materializes the guidance-stripped recipe — exactly the recipe the
root serializes — into every judging room (landed as an ordinary change,
commit `46e6fa5`, admitted by the previous root). This transition rewrites
the spec's justification as an enforced property rather than a false
absolute, and pins the behavior in `kernel_check.py`: two claims differing
only in guidance share one root and must share one verdict, even when the
gate goes reading.

**Finding B — a producer cannot change the question.** Rebuild used to seal
whatever the destination held; a producer that rewrote a pinned input or the
recipe produced a self-consistent claim that was not the source's, reported
as success. The kernel now snapshots the recipe and every pinned input after
materialization (so a caller's deliberate `input_from` threading stays
allowed, exactly as the suite already pinned) and refuses before sealing if
the producer touched them (same commit `46e6fa5`). Pinned here in
`kernel_check.py`: a meddling producer is refused in band.

**Finding C — the record carries the terms of the claim.** `spec/record.md`
promised one predicate over two transports, but a crosscheck whose M1 was a
record never consulted the claim's declared tolerance, cost envelope, or
mutation floor — the record transport could accept what the directory
transport would reject. Record format 2 adds the required `claim` member
carrying those declared obligations; the crosscheck enforces them from a
frozen M1, and a version-1 M1 now yields an *incomplete* verdict on the
declared-conditions check, never a silent pass. Version-1 records stay
readable. Pinned in `exchange_check.py` (emission, validation, the closed
per-version member set) and `kernel_check.py` (a frozen M1 rejects a
measured overrun; a version-1 M1 is incomplete).

## Direction and blast radius

All three edits are essence-restoring: each closes a place where something
that cannot decide acceptance leaked into a verdict, or a promise the spec
made was not enforced. The equivalence class narrows only for pathological
members — an implementation whose gates read guidance, a producer that
edits the question, a record transport used to launder dropped conditions.
No honest claim's root moves; no conforming implementation fails. The going
rate for a rebuild rises only by the three new pinned behaviors, each of
which a correct implementation already has.

Two layer self-claim roots moved with their criteria, exactly the two the
lockfile should notice: `crosscheck` (the kernel suite's three new pins) and
`exchange` (record format 2 in its suite), re-pinned in `self_check.py` with
a dated note. Every other layer held.

One more boundary line rode along, witnessed rather than planned: the
repository's own audit timed out at the default ten-minute gate ceiling —
the acceptance suites have outgrown it under a sandboxed room — so the
recipe now declares `gate_timeout = 1800`. A claim whose own deep check
cannot finish inside its ceiling is not auditable, and "re-earn it here"
is the product; the declared half hour is the honest commitment.

The record-format bump is append-only per the compatibility promise
(`docs/compatibility.md`): both versions read, version 1 write support is
retired in the reference tool, and the change is loud — a version-2 record
refuses under an old reader with the version named in the refusal.

## The bar this click met

An internal ratchet click, held to the internal bar: reseal, `python3
gate.py` green at the new root (every suite, `repo-ok`), a fresh `ret audit
.` receipt, this recorded old→new pair, and a room refresh to follow on
merge. Deliberately unsigned; no agent signs. Prepared on the branch
`transition/room-matches-the-name`; the keyholder's merge is the acceptance
of this transition, per the standing stop-before-root-moves rule.
