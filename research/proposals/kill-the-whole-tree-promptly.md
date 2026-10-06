# Proposal — a timed-out gate dies promptly, process tree and all

*Staged 2026-10-06, from closure trial 1 second attempt (r6). A
contract decision for the keyholder; nothing here moves a root until
signed.*

## The finding

The r6 kernel refuses a gate that exceeds its limit with the right
verdict (`timeout`, jail named) — and takes on the order of the GATE'S
OWN RUNTIME to say so: a `sleep 30` gate under a 1-second ceiling is
reported at ~30 seconds, not ~1. The likely mechanism is the classic
one: the kill reaches the shell and the orphaned child keeps the wait
hostage (the original carries `_kill_tree` for exactly this).
kernel_check's existing probe catches the symptom only through a
wall-clock bound (`< 10 s`) that the r6 behavior straddles —
reproducibly failing in one workspace, passing inside an audit room —
so the chain build under the r6 tree is FLAKY at the crosscheck layer:
the worst kind of criterion, one whose verdict depends on scheduling.

## Why this is worth a pin

A declared ceiling is the claim's own cost bound; a kernel that honors
it only after the runaway work completes converts every hostile or
buggy gate into a denial-of-service against the auditor, and converts
the ceiling into a lie with correct paperwork. Promptness IS the
promise; the verdict word alone is not.

## What must be pinned if accepted

Sharpen the existing probe rather than add one: the refusal must land
within a small multiple of the limit (e.g. limit × 3 + 2 s — generous
to slow hosts, an order of magnitude under the runaway's runtime), and
a probe whose gate SPAWNS A CHILD that outlives the shell must still
be refused promptly (the tree dies, not just the shell). One criteria
edit (kernel_check; arguably a twin in run_check for run_gate itself)
— a root move — hence the signature gate.

## The alternative, named honestly

Keep the generous bound and accept flaky chain builds plus
hostage-priced timeouts. Nobody wants this; the proposal exists so the
decision is recorded, not because the alternative is live.
