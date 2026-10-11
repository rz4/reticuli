# The control falsified the contraction: a correction

*2026-10-11, within the hour of the claim it corrects. Generation 4,
three codex samples at an UNCHANGED S_2, preregistered in
generation-3-contraction.md before the run. The control did its job: it
refuted the result that motivated it.*

## What I claimed, and what the control says

Generation 3 reported "**divergence contracted 25% after one signed
repair**" (65.7 → 49.5 per sample, codex-only). The control, same
boundary, no new pins:

    gen 2  (S_1)            52, 66, 79        mean 65.7
    gen 3  (S_2)            52, 47            mean 49.5   <- the claim
    gen 4  (S_2, UNCHANGED) 74, 68, 47        mean 63.0   <- the control

The control's mean (63.0) is statistically indistinguishable from
generation 2's (65.7) and **higher** than generation 3's. Pooling by
BOUNDARY, which is the correct grouping:

    S_1  [52, 66, 79]              mean 65.7  sd 13.5
    S_2  [52, 47, 74, 68, 47]      mean 57.6  sd 12.6
    difference 8.1 = 0.64 pooled sd

**There is no measurable aggregate contraction.** The within-boundary
spread (sd ≈ 13 on a mean of ≈ 60) is LARGER than the difference I
reported as an effect. Generation 3's "-25%" was two lucky samples.
The claim is withdrawn.

## The program-level audit, re-run with the control's data

The program-family numbers also moderate once the control's three
samples join (generation 3 alone had two, so programs that merely went
UNSAMPLED looked "closed"):

                                   claimed (gen3 only)   corrected (gen3+gen4)
    permissiveness programs, S_1          26                    24
    ... at S_2                            15                    23
    CLOSED and staying closed             18                     9
    persisting                             8                    15
    NEW at S_2                             7                     8

So: **9 families genuinely closed and stayed closed across five S_2
samples; 8 new families appeared; net 24 → 23.** Flat.

## What is actually established, stated carefully

1. **The pins close what they aim at.** Nine program families that
   diverged at S_1 did not diverge in any of five samples at S_2. That
   is a real, directional effect, and it is the part of the gen-3 claim
   that survives.
2. **New strata open at nearly the same rate.** Eight new families
   appeared, robustly (in both generations at S_2): pattern
   destructuring (`. as [$i]`, `. as {$a, $b:[$c,$d]}`, …) and
   `@base64d`. Closing silence revealed silence at ≈1:1 in this regime.
3. **The aggregate divergence count is the WRONG INSTRUMENT at this
   sample size.** The preregistered "killer graph" (disagreement vs
   generation) needs n ≫ 3 per generation to resolve a 10–20% effect
   against sd ≈ 13. Reported as an instrument failure, not a
   discouraging data point.

## The honest consequence for the preregistration

P5 (the stepwise curve) **cannot be scored**: neither the success shape
nor the failure signature is distinguishable at this n. The curve as
designed is under-powered. That is the finding.

## The fix, specified

- **Metric change.** Stop reporting aggregate M. Report, per program,
  the FRACTION OF SAMPLES that diverge — a per-program divergence rate.
  It is stable under sample-to-sample variation in a way the sum is
  not, and it measures the thing the pins actually act on.
- **Power.** ≥ 10 samples per boundary before any contraction claim.
  Codex is un-metered; this is wall-clock, not money. Roughly three
  hours per boundary at observed rates.
- **Nothing is staged for signature.** No repair should be signed on
  the strength of a measurement this noisy, and the ambiguity-zone
  elections (which are judgment calls, not measurements) are unaffected
  and still await the keyholder.

## Why this episode belongs in the record

The control was preregistered in the same document that made the claim,
run immediately, and reported against the claim within the hour. The
mis-pin withdrawals in the self-hosting arm (the dedup-key diagnosis,
the silent-truncation facet) have the same shape: a measurement
outranked a story the agent found compelling. The method's value is not
that it avoids wrong results — it is that wrong results do not survive
contact with their own controls.
