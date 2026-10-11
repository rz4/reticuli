# jq generation 2, scored against the preregistration

*2026-10-11. Three codex samples at S_1 (root 05c83a25a405), each grown
blind, probed on the same 1,395 deterministic novel probes, destroyed.
H-shadow frozen independently (340 probes where gojq or jaq splits from
reference jq — 24.4% base rate). Scorer: score_generation.py; data:
baseline/probes_g2_*.json, oracle_splits.json, generation_score.json.
The claude leg failed at producer launch (plan quota, rc=1) and is
pending — the generation is scored on three samples, not four.*

## The numbers

    sample                M    on-shadow
    codex_s2             52      43 (83%)
    codex_s3             66      44 (67%)
    codex_s1             79      47 (59%)
    pooled (distinct)    92      51 (55%)

    agreement structure:  43 probes flagged by ALL THREE samples
                          19 by two
                          30 by one

## P2 — concentration: SUPPORTED, strongly

Pooled M lies on human-split probes 55.4% of the time against a 24.4%
base rate: **2.27× enrichment**. And the sharper form: of the 43 probes
where ALL THREE independent samples diverge from reference jq,
**40 (93%) are probes where a human implementation also disagrees**.
Where independent machine draws converge on a divergence, human
reimplementers had already disagreed. The model samples and the human
teams are finding the same silence.

## P1 — recall: NOT MET at this sample count

Predicted ≥30%; measured **15.0%** (51 of 340 human-split probes
surfaced by the pooled generation). Reported as a falsification, with
two honest qualifications, neither of which rescues it:

- The prediction named "the evaluation-core stratum of H"; the shadow
  used here is the unstratified split set, which is a *larger*
  denominator than the prediction's. A stratified denominator would
  raise the ratio — but the stratification was never defined
  operationally, so the clean reading is the one reported: not met.
- Three samples, not the generation's planned cardinality (the claude
  leg is pending). Recall accrues sublinearly — the three samples
  overlap heavily (43 of 92 shared by all three) — so reaching 30%
  plausibly needs many more draws, i.e. the prediction was optimistic
  about how fast independent samples decorrelate.

The honest conclusion: **sampled silence concentrates where humans
disagreed (P2) but covers it slowly (P1).** Convergent priors are a
narrow aperture, exactly as negative-space.md's "two grounds" warned;
the fix is more and more diverse producers, not more probes.

## P3 — novelty: ZERO candidates, and the reason is informative

Strict criterion: a both-ok value divergence, off the human shadow,
flagged by ≥2 independent samples. Measured: **0**. The off-shadow
multi-sample set (19 probes) is *entirely* of one class —
`(sample ok, jq error)` — i.e. the samples SUCCEED where reference jq
and both human implementations ERROR: `to_entries` and `transpose` on
wrong-typed input, `index("")`, `del` with mixed slices, `path(.foo[0,1])`,
`indices([1,2])`. That is not novel ambiguity; it is the samples being
**more permissive than the language**, which is a defect class — and a
genuine S_0 under-specification, because the corpus only contains the
error cases somebody thought to write down.

## The generation's yield: two repair classes for S_1 → S_2

1. **Error-condition pins (46 probes, the largest class).** jq errors;
   conforming members must too. The repair: law-style criteria asserting
   that generated wrong-typed/edge inputs to the named builtins RAISE.
   Oracle-free (the error conditions are documented in the manual) and
   witnessed by three independent samples failing the same way.
2. **The true ambiguity zone (15 on-shadow both-ok value divergences).**
   `contains("")` and null-byte containment, `try/catch` error VALUES,
   `join` on heterogeneous arrays, `@uri`/`@html` escaping,
   negative-index slices — where even gojq and jaq disagree with jq.
   Pinning these is a CHOICE: domestication means electing reference
   jq's resolution and recording it as a signed decision, since no
   oracle-free law can settle them. **Keyholder's call, one by one.**

## Instrument notes, recorded

- Three-sample agreement (43/92) means the probe battery is measuring
  structure, not noise: independent draws hit the same loci.
- The hot-program list is stable across samples and reads as the
  divergence literature's contents: contains/index on empty and null
  bytes, try/catch error values, path/setpath/del edges, fromjson,
  join, transpose, to_entries.
- The claude leg must run before the generation is closed: a second
  family is the only available widening of the aperture P1 measured as
  narrow.
