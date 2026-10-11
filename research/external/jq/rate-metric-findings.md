# The rate metric: what the aggregate count was hiding

*2026-10-11, immediately after the control's correction. The fix
specified there — per-program/per-probe divergence RATES instead of
aggregate counts — applied to the data already in hand (3 codex samples
at S_1, 5 at S_2). Instrument: rate_metric.py. A powered campaign to
n=10 per boundary is running; these are the n=3/n=5 readings.*

## The paired comparison the aggregate count could not make

A rate is the fraction of a boundary's samples that diverge at a given
probe. One unlucky sample moves a rate by 1/n instead of contributing
its whole divergence budget, so rates survive the sample-to-sample
variation that destroyed the aggregate reading.

    S_1 (3 samples): 92 probes diverge at all; 43 in EVERY sample;
                     mean rate over divergent probes 0.71
    S_2 (5 samples): 108 probes diverge at all; 35 in EVERY sample;
                     mean rate over divergent probes 0.53

    PAIRED, per probe, "consistent" = diverging in >=2/3 of samples:
      CLOSED (consistent at S_1, never at S_2):   10
      HELD   (consistent at both):                36
      OPENED (never at S_1, consistent at S_2):    1
      net closure                                 +9

**Ten closed against one opened.** That 10:1 asymmetry is directional
and robust, and it is invisible to the aggregate count (which moved
65.7 → 57.6, well inside its own noise). Two further signs in the same
direction: the count of probes diverging in EVERY sample fell 43 → 35
even though S_2 has MORE samples (making unanimity harder to achieve,
not easier), and the mean rate over divergent probes fell 0.71 → 0.53 —
what divergence remains is sporadic rather than systematic.

## Causal, targeted, named

The closed programs, with their rates:

    to_entries                        1.00 -> 0.00
    [first(range(.)), last(range(.))] 1.00 -> 0.00
    try strflocaltime(...) catch .    1.00 -> 0.00
    indices([1,2])                    0.67 -> 0.00

`to_entries` and `indices` are **explicitly in S_2's error laws**. They
went from diverging in every (or two thirds of) samples to diverging in
none. The pins closed exactly what they named, at full consistency.
That is the method's core claim, measured, with the causal chain
visible end to end: measured divergence -> signed law -> divergence gone.

## Two corrections to my own previous readings

1. **The "new destructuring stratum" is NOT established.** Those seven
   programs diverge at rate 0.40 at S_2 (two of five samples) and 0.00
   at S_1 — but with only three S_1 samples, a 0.40-rate phenomenon is
   missed entirely 22% of the time. **Real new zone and S_1
   undersampling are indistinguishable at this n.** Withdrawn pending
   the powered campaign. (It is not single-sample noise either — 0.40,
   not 0.20 — so the question is live, not dead.)
2. **Only 3 programs open CONSISTENTLY at S_2**: `flatten`,
   `flatten(3,2,1)`, `index("!")`. All three are in the ambiguity zone I
   deliberately refused to pin (jq, gojq and jaq disagree on `flatten`
   of a non-array and on the `index`/`contains` family). So the
   consistently-open set is exactly the unpinned set — coherent, not
   mysterious.

## Status of the preregistration

P5 remains unscored, but it is now measurable: the paired rate
comparison is the instrument P5 needed, and the powered campaign
(n=10 per boundary, codex, un-metered, ~4 hours) is running. The
contraction claim will be re-made or abandoned on that data, not on
this.
