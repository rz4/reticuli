# Proposal — a declared input may be a pattern, on both sides

*Staged 2026-10-07, from closure trial 2 (r10, the claude lineage) —
the second family's first contact with this boundary. A contract
decision for the keyholder; nothing here moves a root until signed.
Signing it resets the closure count, which is discussed at the end.*

## The finding

`pack` takes `generated` and `inputs` as lists that may contain glob
PATTERNS; the original expands both. The r10 kernel expands only
`generated`, and passes an `inputs` pattern through to the recipe
verbatim — so `scripts/selfclaim.py`'s `inputs=["checks/*.py"]`
becomes a declared input literally named `checks/*.py`, and `seal`
refuses:

    could not hash a declared file in '…/chain/core':
    [Errno 2] No such file or directory: '…/chain/core/checks/*.py'

Reproduced three ways: the judge's substituted full gate (21 s), a
hand-built substituted workspace, and the true materialized audit
room. One cause.

`authoring_check` passes a PATTERN for `generated` (`"pkg/*.py"`) and a
LITERAL filename for `inputs` (`"check.py"`) in every fixture it has.
So the expansion is exercised on exactly one side of a symmetric
parameter pair, and a conforming implementation can implement exactly
the exercised half. The chain cannot be built without the other half,
which is why this surfaces as an identity refusal rather than a
cosmetic difference.

## What must be pinned if accepted

`authoring_check` passes a glob pattern for `inputs` in at least one
fixture and asserts the recipe's declared inputs are the EXPANDED
file list (and that the claim seals and verifies). One fixture edit
beside the ones already there — a criteria edit, so a root move, hence
the signature gate.

## Why this one is worth the reset

By the k = 3 rule, an adopted counterexample returns the count to
zero. Trial 1 (r9) qualified against this boundary, and this finding
shows the boundary was incomplete when it did — not wrongly judged
(r9 is a conforming member; it expands both sides) but incompletely
specified. The honest options are:

- **Sign it.** The count returns to 0 and the next three trials run
  against a boundary that one more foreign prior could not slip
  through. The seam is load-bearing: a pack without it cannot build
  this repository's own chain.
- **Decline it** and keep the count at 1, with a known hole and a
  published bar whose first qualifying trial is known to have been
  measured against an incomplete specification.

The proposal recommends signing. The reset is not a setback; it is the
rule doing exactly what it was written for — and the fact that it
costs a qualified trial is precisely what makes the eventual count
mean something.

## The second-family lesson, recorded

Five consecutive codex generations closed every seam a codex prior
exposed, reaching zero new seams at r9. The claude prior found one on
its first contact, in a place codex never touched — because codex's
pack happened to expand both sides. That is the era caveat, measured:
the boundary was prior-shaped, and the measurement of how much is
"one load-bearing seam in twenty layers, plus one unpinned verdict
word" (see `pin-the-other-half-of-the-vocabulary.md`). Far better than
"prior-specific" would predict; not "complete".

## Status

Signed by the keyholder 2026-10-07 ("I sign off, next r") and landed
the same day as one bundle with its sibling (see the provenance record
revision-2026-10-07-the-second-family-bundle.md). Adoption reset the
closure count from 1 to 0, as the bar requires.
