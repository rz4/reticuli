# jq generation 3 — the contraction curve's first interval

> **SUPERSEDED, same day.** The generation-4 control (preregistered at
> the bottom of this document) refuted the -25% contraction reported
> here: at an UNCHANGED boundary, divergence came back at 63.0 against
> this generation's 49.5, and the within-boundary spread is larger than
> the effect claimed. See generation-4-control-CORRECTION.md. What
> survives: nine program families closed and stayed closed; the new
> destructuring stratum is real; the aggregate metric is under-powered.

*2026-10-11. Two codex samples at S_2 (root 05ee9161db52, the error
laws). The claude leg failed twice at producer launch (plan quota), so
this generation is codex-only and the fair comparison is codex-to-codex,
per sample. Samples destroyed; measurements in baseline/probes_g3_*.json.*

## The measurement (codex-only, per-sample means)

                            gen 2 (S_1)   gen 3 (S_2)   change
    samples                      3             2
    M per sample            65.7 (52-79)  49.5 (47-52)   -25%
      permissive (ok,error)      35.3          27.5       -22%
      value split (ok,ok)        19.3          13.0       -33%
      sample error (error,ok)    10.0           8.0       -20%
    residual on human-shadow      68%           77%       +9 pts

**Divergence contracted 25% after one signed repair**, and the residual
is MORE concentrated on the loci where human reimplementers disagree
(68% → 77%). That is the predicted mechanism, visible: the pins close
the DETERMINATE silence, and what survives is increasingly the
GENUINELY AMBIGUOUS silence — the part no law can settle.

## Did the pins close what they aimed at? Program-level audit

    permissiveness programs, gen2 -> gen3
      CLOSED   18   del(.[1],.[-6],.[2],.[-3:9]), ascii_upcase,
                    @base64d, .[] | join(","), .[] //= .[0],
                    add({(.[]):1}) | keys, [first(range(.)), ...], ...
      PERSIST   8   the contains("")/null-byte family (5 programs),
                    path(.a[path(.b)[0]]), map(try .a[] catch ...),
                    .foo[.baz]
      NEW       7   ALL destructuring: `. as [$i]`, `. as {$a, $b:[$c,$d]}`,
                    `. as {as: $kw, "str": $str, ("e"+"x"+"p"): $exp}`, ...

Three distinct, interpretable behaviors:

1. **Closed (18).** Exactly the laws' aim. The pins work.
2. **Persisting (8) — correctly so.** Five of eight are the `contains`
   family, which was DELIBERATELY excluded from the laws because jq,
   gojq and jaq disagree there. Their persistence is the ambiguity zone
   refusing to be closed by law, as designed — not a missed pin.
3. **New (7) — all destructuring.** As the error surface closed, the
   samples' remaining divergence MOVED STRATUM, into pattern
   destructuring semantics the earlier generations never reached.
   New silence revealed by closing old silence: the ratchet's expected
   behavior, observed on external software for the first time.

## What this does and does not establish

**Does:** one interval of the contraction curve, with the right
internal structure (drop concentrated in the pinned class; residual
shifting toward ambiguity; a new stratum appearing).

**Does not:** distinguish the preregistered success shape (STEPWISE:
flat within a generation, dropping between) from the preregistered
FAILURE signature (smooth monotone decline = generator drift, priors
converging on each other rather than the boundary constraining them).
One interval cannot tell those apart. Small-n too: three samples vs two,
with wide spread (52–79 vs 47–52), so -25% is suggestive, not
conclusive.

## The control this demands, and it is free

**Generation 4 at an UNCHANGED S_2.** No new pins, same boundary, fresh
codex samples. The two hypotheses predict opposite results:

    specification closure  ->  M stays ~49.5 (FLAT within a generation)
    generator drift        ->  M keeps falling with no pins landed

This is the experiment that makes the curve's shape falsifiable rather
than decorative, it costs nothing on the un-metered path, and it is
preregistered here BEFORE the run. Launching immediately.
