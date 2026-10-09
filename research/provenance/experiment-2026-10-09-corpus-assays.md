# The corpus assays: convergence, performance, and the first instrument-found seam

*2026-10-09, at root `71fd7559…`. Instrument runs over the regrown-tree
corpus (gen0 + r9, r11, r18 codex; r14–r17 claude). No root move; one
proposal staged from the findings.*

## 1. Convergence (the centroid question)

Asked whether the class has a canonical member. Answer: no. 32 of 37
modules show eight distinct AST shapes in eight realizations; whole-tree
mean similarity 0.12–0.18; module size spreads to 12×. The class is
bimodal by family — codex 4,384–4,842 lines (within-family similarity
0.317), claude 8,381–8,638 (0.201), cross-family 0.123 — and gen0 is the
least typical member of its own class (0.074). Convergence tracks pin
density (core 0.377 … dispatch 0.024), and every trial seam to date sits
at a low-convergence locus. Full gradient and gene table:
research/metrics/genome-map.md.

## 2. Performance (measure before pinning)

Every realization ran the same micro-workload as the acting tool, same
host, nice'd, median of 3: seal / verify / audit (sandboxed gate) /
rebuild (printf producer). Result: FLAT — all eight realizations within
~1.7× on every verb (seal ~0.022s, audit 0.027–0.038s, rebuild
0.033–0.057s). At this scale there is no performance divergence to pin;
the known risk is algorithmic blowup at depth (the 23G copytree lesson),
which a micro-workload cannot see. A scaling assay (deep chains, many
files) remains open; no perf pin is justified by current evidence.

## 3. The audit_deep timing anomaly → the first instrument-found seam

The assay's audit_deep column was NOT flat: r17 at 0.000 and r14/r15 at
half of everyone else. Those were not speed — they were walkers not
re-earning the fixture's component. Unwinding it:

- r17 enumerates the chain from the recipe's `from` fields only; a
  manifest-only component (the pulled-data shape) is invisible to it —
  it walks ZERO layers and reports ok.
- Then the forgery witness: a dependent that pins a component's data
  output as an input, declares the attribution via seal_with, then ships
  FORGED bytes under a reseal. Measured verdicts, shipped tool included:
  verify True, audit True, audit_deep True, deps edge "ok". EVERY
  realization false-passes. The data half of the component contract is
  seal-time-only: detect_components content-matches once, nothing
  re-earns it, and sign_root folds the (now false) attribution into
  signed identity.

Staged: pin-data-dependency-re-earn (a criteria edit AND a src fix —
the shipped tool fails the fixture today; precedent, the 2026-09-28
soundness closures). This is the first seam selected by an instrument
rather than a trial refusal: the corpus assay found at analysis-speed a
gap that eighteen trials never exercised, in the shipped semantics
itself. The instrument-recursion thesis, demonstrated on its first
outing.

## Status of the pending-pin set at this root

Measured and staged, awaiting the keyholder's batched boundary move:
flat-store resolution (bites r15+r18, passes shipped), data-dependency
re-earn (bites EVERYTHING including shipped). Forward: copy-compactness.
Each adoption resets the count (1 of 3, r17); one batched reset
dominates several.
