# Proposal — pin the other half of the verdict vocabulary

*Staged 2026-10-07, from closure trial 2 (r10, the claude lineage). A
contract decision for the keyholder; nothing here moves a root until
signed. The finding also qualifies how much a "clean" instrument row
is worth, which matters for how trial 1 is reported.*

## The finding

`surface_check` pins the verdict vocabulary in one direction only: a
failed gate is reported `failed`, and specifically **never** `broken`.
Nothing pins what `audit` reports when a claim's identity is damaged —
when a pinned input was flipped after sealing, and the claim is not
what its name says. The word `broken` is the one the original uses and
the one the documentation means; no criterion requires it.

Measured across ten conforming implementations on a tampered-input
claim, the word for identity damage is:

    broken             original, codex-r4, codex-r5, codex-r6, codex-r9
    earned             claude-g1 (r3)
    error              codex-g1 (r3)
    failed             codex-r7
    identity mismatch  codex-r8
    mismatch           claude-r10

Six words for one condition. Every one of those trees passes
`surface_check`, because the pin only forbids `broken` where `failed`
belongs and is silent in the other direction. `claude-r10` chose
`mismatch` — a word that is legitimately in `spec/verification.md`'s
GATE-status vocabulary, borrowed for the identity case. A defensible
reading of an underspecified contract, which is exactly the species
this project exists to find.

## Why it is worth pinning

A recipient automating against the tool reads `status` to decide
whether a claim is DAMAGED (do not trust these bytes; restore them) or
whether its GATE FAILED (the bytes are intact; the criteria refused).
Those demand different responses, and today the word distinguishing
them is implementation-defined. `failed` appearing for identity damage
(codex-r7) is the dangerous case: it reads as "the claim is fine but
its tests fail," which is the opposite of the truth.

## What must be pinned if accepted

`surface_check` gains the mirror of its existing assertion: `audit
--json` on a claim whose pinned input was changed after sealing
reports `status == "broken"`, and its gate rows do not call that
condition `failed`. One assertion beside the one already there — a
criteria edit, so a root move, hence the signature gate.

## The uncomfortable corollary, recorded deliberately

Trial 1 (r9) was reported with a "clean matrix row — zero findings of
its own." That remains true as written, and the trial's qualification
never depended on this word (the bar's conditions are the gate, verify,
crosscheck, and the recursive step; the cross-judging matrix is an
extra instrument). But r9 said `broken` because it happened to draw
that word, not because anything required it. A clean row can hide an
unpinned seam whose draw matched the pinned value, and the honest
reading of trial 1 is "clean, including one coin-flip it won."

That is an argument for the bar needing two families rather than
three runs of one — which is what it says — and for this pin landing
before trial 3, so the next clean row means more than the last one.

## Status

Signed by the keyholder 2026-10-07 ("I sign off, next r") and landed
the same day as one bundle with its sibling (see the provenance record
revision-2026-10-07-the-second-family-bundle.md). Adoption reset the
closure count from 1 to 0, as the bar requires.
