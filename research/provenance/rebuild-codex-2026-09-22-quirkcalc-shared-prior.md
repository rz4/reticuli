# quirkcalc basin pilot, generation 0 — the shared-prior blind spot (codex, 2026-09-22)

The contraction experiment on a *genuinely underdetermined* subject, and the
single most important finding of the pilot program: **disagreement between
independent rebuilds is not the same as distance from the intended behavior.**
When the rebuilds share a prior, they agree with each other on a wrong answer,
and a rebuild-vs-rebuild differential is blind to it.

## What was run

- **Subject:** `quirkcalc` — an integer expression evaluator with *invented*
  semantics (`~` digit-join, `?` max, `%` floor-average, right-associative
  additive/multiplicative levels, `/` truncating toward zero). None of it is
  guessable; it lives only in the cases.
- **Boundary `C_0`:** deliberately partial — 12 cases establishing that the
  operators, basic precedence, and parentheses exist, with associativity, the
  meanings of `? % ~`, and every edge case left open. Root `1ef7e8baa30c`.
- **Producer:** codex, `k = 8` blind rebuilds across `gpt-6-luna/sol/astra`.
- **Ground truth:** the reference `calc.py`, used as an adjudication oracle.

## Result

    generation 0: R=1.0 (8/8)  S=0.228 (1 cluster)  D=0.0156
    vs ground truth over 391 probes: 258 correct, 121 SHARED MISSES, 12 split

All eight rebuilds pass `C_0`. Among *themselves* they barely disagree
(D = 0.0156 — about six probes, two classes): truncation direction on
`(0-7)/2`, and one `?`/`~` interaction. But against truth, **121 of 391 probes
are shared misses — every rebuild agreeing on the same wrong answer** — and only
12 are genuine inter-rebuild splits. Examples, all eight identical and all
wrong:

| expression | all rebuilds | true quirkcalc |
|---|---|---|
| `10 - 3 - 2` | 5 | 9 (right-associative) |
| `100 / 5 / 2` | 10 | 50 |
| `24 / 4 * 2` | 12 | 3 |
| `8 % 2 * 3` | 15 | 7 (`%` = floor-average) |
| `23 ? 10 % 5` | 23 | 14 |

The rebuilds converged — on *standard calculator semantics*, which quirkcalc is
not. The 12 cases underdetermined the quirks, and every model filled the gap
from the same shared prior.

## The finding

The rebuild-vs-rebuild differential saw ~6 disagreeing probes. The truth
comparison saw 133 wrong. **The shared-prior blind spot is ~20× larger than
what inter-rebuild disagreement reveals.** A contraction loop driven purely by
disagreement among rebuilds would read D ≈ 0, declare the basin converged, and
be wrong about 31% of the behavior — a false convergence.

This is falsifier F2 (producer dependence) made concrete and measurable, and it
sharpens the whole method:

- **Disagreement ≠ error.** Contraction must be driven against something
  outside the reconstruction population — a ground-truth oracle where one
  exists (as here), or genuinely independent producers whose priors differ.
- **The cross-family control is not optional.** One family shares one prior;
  where that prior is wrong, no amount of within-family sampling (even across
  sizes, as here) surfaces it. A different family might — unless the wrong
  prior is shared across families too, which is exactly what the held-out
  control is there to detect.
- **The instrument can measure the blind spot** when a truth oracle is
  available: the `survey --oracle` path reports correct / shared-miss / split,
  so a false convergence is visible rather than hidden behind D ≈ 0.

## What it leaves

Two keyholder options, nothing ratcheted:

1. **Adjudicate toward truth, then contract.** Accept a batch of shared-miss /
   split witnesses as counterexamples (each `expression -> true value`), build
   `C_1`, re-run, and measure whether shared misses shrink across generations.
   This demonstrates contraction *with a truth oracle in the loop* — and shows
   the curve is driven by the oracle, not by inter-rebuild disagreement.
2. **Bring in a second family.** Re-run generation 0 with a genuinely different
   producer family and test whether it breaks the shared prior — the real F2
   control. If a different family still shares the standard-calculator prior,
   that is itself a strong (and sobering) result.

The instrument, generalized across subjects and now ground-truth-aware, is
validated on three real generations (base64 stdlib, base64 from-scratch,
quirkcalc) and ready for either.

## Cross-family control — the second family breaks most of the blind spot (2026-09-22)

A `claude` producer was added (`src/reticuli/producers/claude.py`, the Anthropic
family, un-metered on the subscription) and eight more blind rebuilds run
(4 sonnet, 4 opus). Surveying the **combined 16** (8 codex + 8 Claude) against
truth, beside the codex-only run:

| population | correct | shared misses | split | clusters | D |
|---|---|---|---|---|---|
| codex only (8) | 258 | **121** | 12 | 1 | 0.016 |
| codex + Claude (16) | 202 | **29** | 160 | 6 | 0.143 |

The second family **broke ~76% of the shared misses** — of codex's 121 probes
where every rebuild agreed and was wrong, ~92 became splits once Claude
disagreed. Inter-rebuild disagreement rose from 12 probes to 160, and structural
diversity from 1 cluster to 6. So producer diversity is a *real* remedy for
producer dependence, not a null one.

A correction to the earlier n=1 note: a single sonnet rebuild happened to match
codex on the six corners first inspected, which read as "the prior is shared
across families." The full batch shows that was an artifact of a tiny sample —
across 391 probes the two families disagree constantly. The honest finding is
the middle one:

- **Cross-family diversity substantially breaks shared blind spots** (121 → 29),
  and surfaces far more real questions (12 → 160 splits) for the ratchet.
- **But it is not sufficient.** 29 shared misses survive *both* families — probes
  where OpenAI and Anthropic are wrong the same way (a deeper shared prior).
  Only a ground-truth oracle (or a genuinely divergent third family) catches
  those.

Both levers matter, and the instrument measures each: producer diversity shrinks
the shared-miss set, and the oracle catches the residue diversity cannot. This
is the practical shape of the F2 control — not "diversity fixes it" or
"diversity is useless," but a measured split between what more producers buy and
what only truth can.

## Generation 1 — the first contraction step, with structure preserved (2026-09-22)

The keyholder ratified ten counterexamples (each `expression -> true value`,
spanning the missed rules: right-associativity, `%` floor-average, `?` max
precedence, `~` digit-join and its negative-right error, `/` truncation).
`C_0 -> C_1` moved the claim root `1ef7e8baa30c -> d7387dd56d49`. Both families
were re-run against `C_1` (8 codex + 8 Claude) and the combined 16 surveyed
against truth:

| metric (16 rebuilds, 391 probes) | C_0 | C_1 |
|---|---|---|
| correct | 202 | **322** |
| shared misses | 29 | **0** |
| splits | 160 | **69** |
| behavioral diversity D | 0.143 | **0.084** |
| structural diversity S | 0.483 | **0.513** |
| structural clusters | 6 | **7** |
| open questions vs truth | 35 | **7** |

This is the pre-registered success signature, observed on a real subject with
real independent cross-family rebuilds: **behavioral error and diversity
contracted (correct +59%, shared misses to zero, splits −57%, D down) while
structural diversity was preserved and if anything rose (S up, 6 → 7 clusters).**
Ten human-ratified rules pulled sixteen structurally distinct implementations
(Claude ~4.5KB, codex ~2.5KB — genuinely different architectures) toward the
true invented behavior without collapsing them onto one implementation. The
boundary is constraining *behavior*, not code.

The seven residual questions are deeper corners the ten rules did not reach
(modulo-by-zero interactions, `?`/`%` precedence residue, right-associative
division like `9*7/4`). A second ratchet step would close them — the curve
continues.

Honest scope: contraction here is driven by a ground-truth oracle (the
counterexamples were adjudicated against the reference). In a subject without a
reference, the keyholder's judgment is the oracle, and the same loop applies.
This is one generation of one subject — a first point on the curve, not the
whole curve — but it is a clean, quantified demonstration that the reconstruction
basin contracts on behavior under a ratchet of human-ratified counterexamples
while implementation diversity survives.
