# Proposal — a component's supplied output may be a nested path

*Staged 2026-10-08, the ISOLATED replacement for the withdrawn
pin-the-deep-audit-dedup-key. This one is measured end to end, not
inferred. A contract decision for the keyholder; a root move, so the
signature gate. Signing resets the closure count (set 3 has no
qualified trial yet, so the reset is free).*

## The finding, reproduced

r13's deep audit crashed on the committed (original-built) chain. The
full traceback reduces to one line — r13's component materialization:

    # registry.py:74 (r13)
    shutil.copyfile(src, os.path.join(into, output))

with no parent directory created first. When a component supplies a
NESTED output — `reticuli/_kernel/__init__.py` — and the room does not
already contain `reticuli/_kernel/`, the copy raises FileNotFoundError.
The original never hits this because its copy helper makes the parent:

    # _kernel/core.py (original _copy_into)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(src, dst)

Both are "materialize the component's supplied bytes." One creates the
directory a nested path needs; the other assumes it exists. The
self-claim chain's components supply `reticuli/_kernel/*.py` and
`reticuli/_cli/*.py` — nested — so this refuses the chain whenever the
directories are not incidentally pre-made.

Why no criterion saw it: `exchange_check`'s deep-audit fixture (base
on mid on top) uses only FLAT outputs. Nested component outputs are
the unexercised half of the staging contract — the fifth-species
pattern, now correctly named. The earlier dedup-key guess was the
wrong half of the wrong contract; this is the right one, with a
traceback behind it.

## What must be pinned

`exchange_check`'s deep-audit fixture gains a component that supplies a
NESTED output (e.g. `pkg/sub/mod.py`), threaded into the dependent and
re-earned through the composed audit. A kernel whose component
materialization does not create parent directories fails to stage the
fixture and is refused. One fixture edit beside the three-claim
chain — a criteria edit, so a root move.

## Honest scope — what this does NOT yet explain

This pin closes the reproduced crash: nested component-output staging.
It is the seam that refuses the self-claim chain on original-built
inputs, and it is load-bearing and measured.

It may not be the WHOLE of what felled r13. The substituted gate's
self_check failed a layer-COUNT assertion rather than crashing, and
that facet was not reproduced standalone (an r13-built chain audited
to the correct 18 unsandboxed). The count discrepancy may be a second,
sandbox-dependent facet of the same staging weakness, or a distinct
seam. The register carries it as still-open; this proposal pins only
what has a traceback. Pinning the measured part and flagging the
unmeasured part is the whole difference between this proposal and its
withdrawn predecessor.

## The cross-family tally, corrected

Three claude draws, three load-bearing seams — input-pattern globs
(r10), the room recipe's syntax (r12), and nested component-output
staging (r13) — each the unexercised half of a symmetric contract
(one-side/other-side; copy/rewrite; flat/nested), each deeper than the
last. The rate reading stands; only r13's mechanism is corrected from
"dedup key" (falsified) to "nested staging" (reproduced).
