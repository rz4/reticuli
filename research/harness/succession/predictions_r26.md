# Predictions for succession r26 — the claude leg at the finite-cost root

*2026-10-14. Root `f9b292af5f46…`, FROZEN. Lineage: claude, the second family.
Grown after the subscription reset, against a boundary r25 itself hardened.*

The count is at zero again: `1d9ab7ed` lasted one trial before r25 produced a
counterexample and the signature adopted it. That is the rule working rather
than thrashing — the boundary is still learning, so the count cannot grow.

One gene is new since r25, and it is the first in this project's history that a
**reconstruction** forced rather than an author:

- **a cost value is finite.** `NaN` and the infinities are refused alongside
  booleans and negatives, in the reader and in the ledger totaller. r25's
  regrown tree already did this; the shipped tree did not, and `value < 0` is
  false for every NaN comparison and for `+Infinity`, which is how it hid.
  Both halves are now criteria, and the shipped reader and totaller were
  repaired to match the reconstruction.

- **P1.** 21/21 grow. claude has done it before; the quota reset is fresh.
- **P2.** The finite-cost gene is a no-op for claude. A producer writing the
  obvious `math.isfinite` guard satisfies it without trying, and the one that
  found it wrote exactly that unprompted. If claude instead reproduces the
  shipped tree's `value < 0` form, the gene refuses it at the attest layer and
  that is a second independent witness that the old wording was ambiguous.
- **P3.** Identity re-earns: the full gate passes with 37 substituted modules,
  confirmed by the same negative control r25 used rather than by the verdict
  alone.
- **P4.** Trial seals as `trial-r26-claude` — count 1 of 3 at `f9b292af`, with
  the claude family banked and the codex leg to re-run.
- **P5.** A new seam, not zero. Predicting zero has been wrong three times
  running, and r25 found one on a surface nothing had probed. The honest
  prediction is that a second independent family finds something the first did
  not, and the interesting question is whether it is on the cost surface again
  or somewhere untouched.

**And a selection prediction, declared before measuring**, since the axes were
fixed before this run: claude's tree lands on the frontier too, trading against
codex's rather than dominating it. r25 came in at 175 KiB with 10 KiB of prose
against the authored 438 and 131. If claude's tree is also near 40% of the
authored size with almost no prose, that is evidence the compaction is a
property of blind reconstruction generally and not of one producer — which is
the claim selection would need before anyone should take a frontier seriously.
