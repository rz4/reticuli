# Proposal — the deep audit stages nested outputs and never silently truncates

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

## What must be pinned — two facets, both measured

FACET 1 (nested staging, reproduced by traceback). `exchange_check`'s
deep-audit fixture gains a component that supplies a NESTED output
(e.g. `pkg/sub/mod.py`), threaded into the dependent and re-earned
through the composed audit. A kernel whose component materialization
does not create parent directories fails to stage the fixture and is
refused.

FACET 2 (silent truncation, confirmed by code diff). The same fixture,
with one mid-chain component's manifest made unreadable, must FAIL the
deep audit (recorded unresolved), not silently return fewer layers.
The original records an unresolvable/unreadable layer as
`{"status": "unresolved", "ok": False}` and fails; r13's `_walk` does
`except kernel.ClaimError: return`, pruning the subtree with no error
and no failure flag — which is exactly a layer-COUNT drop without a
crash, the shape the substituted gate's self_check assertion caught.
Pin that an unreadable layer fails the composed verdict and is counted,
never dropped.

Both are one criteria edit on the deep-audit fixture — a root move, so
the signature gate.

## Honest scope

Facet 1 is reproduced by traceback (the crash on the original-built
chain). Facet 2 is confirmed by code diff — r13 prunes where the
original records-and-fails — and is the mechanism that produces a
count drop without a crash, which is what the substituted gate saw;
but the exact sandbox condition that makes a mid-chain manifest
unreadable under self_check was not reproduced standalone (an r13-built
chain audited to the correct 18 unsandboxed). So facet 2's EXISTENCE as
a soundness gap is certain; its precise trigger in the r13 judgment is
inferred, not reproduced. The fixture pins the gap directly (an
unreadable layer must fail), which closes it regardless of the trigger.
The one genuine loose end: a standalone reproduction of the sandboxed
count drop, left for the isolation follow-up — it would confirm the
inference but is not needed to justify the pin.

## The cross-family tally, corrected

Three claude draws, three load-bearing seams — input-pattern globs
(r10), the room recipe's syntax (r12), and nested component-output
staging (r13) — each the unexercised half of a symmetric contract
(one-side/other-side; copy/rewrite; flat/nested), each deeper than the
last. The rate reading stands; only r13's mechanism is corrected from
"dedup key" (falsified) to "nested staging" (reproduced).
