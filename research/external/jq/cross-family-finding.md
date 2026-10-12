# Repairs are CLASS-specific; visible contraction is FAMILY-specific

*2026-10-11. A claude sample at S_2 (the first; S_2 had been codex-only)
turned a clean negative into the arm's most instructive finding.
Caveat first: claude is n=1 per boundary, so its numbers carry no
statistical weight on their own — the value here is that the class
decomposition EXPLAINS a discrepancy and makes a falsifiable prediction.*

## The negative result

    claude, paired S_1 -> S_2 (n=1 each):
      M at S_1: 34      M at S_2: 34      (aggregate unchanged)
      closed 12 | held 22 | opened 12     sign test p = 0.58

For the claude family the error-law repair produced **no contraction at
all** — perfectly symmetric churn. The codex result (10 closed, 1
opened, p = 0.0059) does not replicate in the other family.

## The explanation, measured

Divergence has three classes, and the two families have different
PROFILES:

                       permissive   value-split   sample-error   permissive share
    codex  S_1            35.3          19.3          10.0            54%
    codex  S_2            27.5          13.0           8.0
    claude S_1             6            17            11              18%
    claude S_2             5            20             9

S_2's repair was **28 error laws** — a repair aimed squarely at the
PERMISSIVE class. And permissiveness fell in BOTH families: codex
35.3 → 27.5, claude 6 → 5. The repair did what it was designed to do,
everywhere.

But permissiveness is **54% of codex's divergence and only 18% of
claude's.** So the same repair moves codex's total measurably and leaves
claude's total untouched. Nothing about the boundary behaved
differently per family; the families simply fail differently.

## What this means (three things, in order of importance)

1. **"Did the specification improve?" is not answerable from one
   family's aggregate.** You need the class decomposition. A repair can
   be fully effective and invisible, if the family you measure does not
   make that class of error. This is a generalization of the instrument
   lesson from this morning: first the aggregate hid the effect by
   discarding pairing, now it hides the effect by pooling classes.
2. **Each producer family is a different aperture on the same silence.**
   codex finds under-strictness; claude finds value divergence. Neither
   is better; they are measuring different parts of the boundary, which
   is exactly why the preregistration required two families — and why
   P1's recall ceiling (17.6%) is a statement about priors, not about
   the method.
3. **A falsifiable prediction, stated before the test exists.** The
   repair that will contract CLAUDE's divergence is one aimed at the
   VALUE-SPLIT class — which is precisely the ambiguity zone awaiting
   the keyholder's election (elections.md: `contains` on non-containers,
   `setpath` on malformed paths, the `index`/`indices` object question).
   **If the elections land as S_3 and a fresh claude sample's value-split
   count drops while its permissive count stays flat, this account is
   confirmed; if claude's value-splits are untouched, it is wrong.**
   Recorded here so the prediction precedes the experiment.

## The loop this closes

The elections were framed as housekeeping — a decision the keyholder
owes the arm. They are not. They are the repair targeted at the other
family's dominant failure mode, and the measurement that would validate
them is now specified in advance.
