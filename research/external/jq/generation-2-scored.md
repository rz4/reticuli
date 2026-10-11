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

---

## Generation closed: the claude leg, and the aperture measured

The claude leg ran (producer launch succeeded on retry) and the
generation is closed at four samples, two families.

    claude_s1   M=34   on-shadow 26 (76%)   agreement with jq 97.6%
    (codex trees agreed 94.3%, 92 pooled M)

**The family signature reproduces on external software.** The claude
sample is 3,263 lines against codex's 869 — a 3.8× size ratio,
independently confirming the ~2× claude/codex divergence signature
measured on reticuli's own corpus. Qualitatively different too: half of
claude's divergences are both-ok VALUE splits (17 of 34) where codex's
were dominated by permissiveness — the claude family diverges
semantically, the codex family diverges by under-strictness.

**P1, final: 17.6%** (60 of 340), up from 15.0% codex-only. The second
family contributed 15 probes the first family never surfaced — so
aperture widening is REAL but MODEST: +2.6 points for a whole extra
family. The prediction (≥30%) stands falsified, and the refined finding
is stronger than the original guess: **the silence two frontier priors
can jointly see is substantially narrower than the silence that
demonstrably exists** (340 probes where human reimplementers disagree).
Diverse producers help at the margin; they do not close the gap. For
the audit product this is the key honest number — sampled
reconstruction finds *a concentrated, high-value fifth* of the
divergence surface, not all of it.

**P2, final: 2.30×** pooled, and the cross-family form is the sharpest
statistic the generation produced: of the 19 probes where BOTH families
diverge from reference jq, **17 (89%) are probes where a human
implementation also disagrees.** Independent machine priors and
independent human teams converge on the same loci. P2 is supported
about as strongly as this design can support it.

**P3, final: 0.** The only two cross-family off-shadow agreements —
`map(delpaths([[0,"foo"]]))` and `map(try .a[] catch ., .a[]?, ...)` —
are both the permissiveness class (both families succeed where jq and
both humans error). No novel ambiguity was found. Honest reading: with
contamination this heavy, the priors reproduce jq's *documented*
semantics well and fail only where jq is *silent* about errors; genuine
novel ambiguity, if it exists in this stratum, is below this
instrument's sensitivity.

## Staged for signature: S_1 → S_2, the error-condition laws

The repair the generation actually earned, oracle-free and witnessed by
all four samples across both families: **jq's error conditions are part
of the specification.** The corpus contains only the error cases
somebody wrote down; every sample was more permissive than the language
somewhere. The criteria to add (law-battery style, gate-time generated
inputs, expectations from the manual not from running jq):

    to_entries / transpose / join / implode on wrong-typed input RAISE
    delpaths / del / setpath on malformed path arrays RAISE
    path(f) where f is not a path expression RAISES
    indices / index / contains with mismatched operand types RAISE
    arithmetic on incompatible types RAISES (object - number, etc.)

A member that silently succeeds where the language errors is not a
member. This is the external arm's second repair, and the first one
whose witness is cross-family.

**NOT staged, deliberately:** the 17-probe true-ambiguity zone
(`contains("")`, null-byte containment, try/catch error VALUES, `join`
heterogeneity, `@uri`/`@html`, negative slices). No law settles these —
gojq and jaq disagree with jq there by design. Pinning them means
ELECTING reference jq's resolution, one by one, as signed decisions.
That is the keyholder's judgment call and the arm's first taste of what
domesticating someone else's software actually costs.
