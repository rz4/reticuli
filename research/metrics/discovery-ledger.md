# The discovery ledger — measuring the loop

*2026-10-03, started at the keyholder's direction. The hypothesis under
test: the cycle `boundary → independent realizations → disagreement →
counterexample → stronger boundary` is producing counterexamples at an
increasing rate because each cycle's outputs include better instruments
for the next. If the slope of discoveries-per-unit-cost rises across
independent cycles, that is evidence of the phenomenon; if it does not,
the feeling of acceleration was a feeling. This ledger is the record
either way.*

## Counting discipline (stated first, because the metric is Goodhartable)

A **discovery** is an *adoptable counterexample*: recorded in
`research/provenance/` or `research/audits/` with reproducible evidence,
and either **promoted** into a boundary (a signed root move, or a shipped
`src` change) or **staged** with a concrete pin attached. Raw divergence
counts do not count — the silence map can manufacture unbounded
"divergences" by growing its probe battery, which is exactly the
inflation the ladder's own finding predicts. A **cycle** is one recorded
experimental campaign with its own question. "Proposed unprompted" means
the machinery or the assistant surfaced the counterexample without the
keyholder directing attention at it; the keyholder choosing *which*
proposal to fund does not make a discovery prompted. Producers are
un-metered subscriptions, so cost denominators are producer-hours (PH)
and analysis-time, not dollars.

## The cycles

| # | date | cycle | discoveries | unprompted | promoted | staged | dominant cost |
|---|------|-------|------------:|-----------:|--------:|-------:|---------------|
| 1 | 09-18 | self-rebuild audit | 6 (canonical-name gap, ssh-keygen undeclared, stale shipped kernel, cost-mixing, CLI-pinnedness corrected, freedom list) | 2 | 3 | 3 | days of PH |
| 2 | 09-22 | cross-family reading | 3 (soundness gaps A/B/C) | 3 | 3 | 0 | hours, 2 models |
| 3 | 09-23 | contraction pilot | 2 (basin contracts on frozen probes; structural diversity rises) | 1 | 0 | 2 | ~1 day PH |
| 4 | 09-28 | substitution stage 2 | 3 (6/6 gate-pass 0/6 consumer; cross-family shared prior; ratchet closes it 6/6) | 2 | 2 | 1 | ~1 day PH |
| 5 | 09-29 | generation ladder | 4 (faithful preserves 8/8×16; minimize collapses in 1 step; attractor = blind prior; canonization mechanism) | 4 | 0 | 4 | ~4 h PH |
| 6 | 09-29 | succession | 8 (pack-surface seam; gate_timeout inversion; rebuild kwarg three-way disagreement; sub-layer private seams; reference.py unowned; scrub credential leak; verdict-vocabulary misuse; tamper-watch residue) | 8 | 2 (clicks A, J) | 6 | ~1 day PH ×2 lineages |
| 7 | 09-30 | succession r2 (reprove) | 3 (substantive refusal gone — clicks verified; performance drift: conforming-but-too-slow for own audit window; click-A self-containment defect) | 3 | 1 | 2 | ~1 day PH |
| 8 | 10-02 | scaling / verdict cache | 4 (audit-as-cache w/ free invalidation; reuse.py already-shipped half; O(frontier) self-audit 17s→0s; repo-pins-more-than-chain) | 3 | 3 src | 1 | hours, mostly analysis |
| 9 | 10-03 | attested shared cache | 2 (fresh-host 0.1s audit via verified earner; scrub leak confirmed by use) | 2 | 1 src | 0 | ~1 h |
| 10 | 10-03 | silence map + closure check | 8 (3 unseen kvparse silences; ratchet contraction measured C0→C1; 4 latent kernel-name gaps; pre-click-A seam re-found statically) | 8 | 5 (click F + 3 pins + instrument) | 3 | minutes, analysis only |

## The early readings (to be re-derived as cycles accumulate)

- **Unit cost of a counterexample**: days of producer-hours (cycles 1–7)
  → minutes of analysis (cycle 10). The mechanism is visible, not
  inferred: cycles 6–7's outputs *were* the instruments cycle 10 ran.
- **Unprompted fraction**: ~0.3 (cycle 1) → 1.0 (cycles 5–10). The
  keyholder's role has moved from directing questions to selecting among
  machine-proposed ones and signing promotions.
- **Promotion lag**: cycle 6 staged 8 and promoted 2; cycle 10 staged and
  promoted in the same day. The **unsigned queue** (staged minus promoted,
  cumulative) is the takeoff governor to watch: adoption is structurally
  rate-limited by the signature, so proposal generation outrunning
  signatures is the early signal — about 12 clicks currently staged
  across the open proposals.
- **The loop closed once, today**: cycle 6 produced cycle 10's
  instrument; cycle 10's instrument produced counterexamples; the same
  signed transition promoted both the instrument and its findings into
  the boundary that judges cycle 11. One full
  instrument-begets-instrument iteration, with exactly one human act in
  it.

## What would falsify the superlinear reading

Three flat or declining cycles of discoveries-per-cost with the
instruments held fixed; or a rising count that collapses under the
counting discipline (clusters inflated by battery growth, findings staged
without pins); or promotion stalling so the "stronger boundary" step —
the step the loop's power actually comes from — stops happening. The
honest competitor hypothesis: a new codebase is target-rich, and the rate
reflects depletion-free early mining rather than compounding instruments.
Distinguishing them needs exactly what this ledger records: whether the
rate *holds or rises* as the easy surface depletes.
