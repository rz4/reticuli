# The bounded-exhaustive gate — decide, don't sample

The first step on the proof body (docs/notes/jester.md): everything before this
was sampler-grade. The differential fuzz asked "did an independent reconstruction
and the reference disagree on N random expressions?" and answered "not in 20k
tries" — strong evidence, but a sampler, and a rarer region can hide below its
resolution. One did: a `/0`-inside-`?` ordering edge at ~1-in-60k, seen in the
v2 round and gone (to the sample) by v3, leaving doubt about whether it was fixed
or merely missed.

This gate replaces the sampler with a **decider** over a bounded domain. It
enumerates *every* quirkcalc expression with up to two binary operators over the
operand set `{0, 1, 2, 5}`, in the parenthesizations the grammar admits (bare, to
exercise precedence and associativity; fully parenthesized, to force structure) —
22,180 expressions — and requires the implementation under test to agree with the
sealed reference semantics on **all** of them: the same integer, or the same
refusal. Passing is not "no divergence in a sample"; it is a **small-scope
theorem** — the implementation *is* the reference on the entire bounded domain.
Artifacts: [`exhaustive/gate_exhaustive.py`](exhaustive/gate_exhaustive.py) and
[`exhaustive/semantics.py`](exhaustive/semantics.py) (the sealed reference).

## Result: strictly stronger than the fuzz, both directions

Run against the v3 vendor draws that had *converged* on the fuzz (Claude and
GPT-5, 100% over 20k) and against known-broken implementations:

| implementation | fuzz said | decider says |
|---|---|---|
| v3 reference | — | ✓ theorem over 22,180 (agrees with itself) |
| v3 Claude draw | 100% (sampled) | ✓ **theorem over 22,180** — no `/0` edge, decided |
| v3 GPT-5 draw | 100% (sampled) | ✓ theorem over 22,180 |
| v2 Claude draw | 98.06% (regression) | ✗ caught on `(0)*(0)~1` — deterministic |
| injected lazy-`?` (`/0`) | ~1-in-60k to catch | ✗ caught on `(0)?(1)/0` — deterministic |

Two things the sampler could not do. It **removed the doubt** the fuzz left: the
`/0` edge is not merely absent from a v3 sample, it is *decidedly absent* over all
2-op expressions (every `x ? y / 0` form is in the domain, and the v3 draws
refuse exactly as the reference does). And it **caught the rare edge on the first
try**: the injected lazy-max bug — return the left operand instead of evaluating
a failing right one — fires on `(0)?(1)/0`, the exact ~1-in-60k region the fuzz
needed luck to reach.

Sealed as a record (`quirkcalc-exhaustive`, root `36a41ad5`): the reference
semantics and the enumerating gate are the dry seeds; `calc.py` is the free
implementation; the basin is now "agrees with the reference on every 2-op
expression," a far tighter spell than "passes 75 hand-written tests." A
byte-different valid draw lands the same root.

## The honest ceiling, moved (not removed)

- **Decided, not proven-for-all.** The theorem is bounded: 2 operators over
  `{0,1,2,5}`. Beyond the bound is unproven. Raising it (3 operators, more
  operands) is exponential, which is the small-scope-vs-full-proof gap in one
  line — you decide a finite frontier and push it outward at rising cost.
- **Differential, and it trusts the reference.** The gate decides *impl ≡
  reference*, with the reference (a 111-line evaluator) trusted by inspection. A
  fully formal gate (move 3) would prove properties of the *semantics itself* and
  carry a machine-checked proof, needing no reference to trust. Bounded-exhaustive
  is the rehearsal: it establishes the *shape* — decide over a domain, catch what
  a sampler misses — one rung below a proof.
- **No compression here.** For quirkcalc the sealed semantics is as large as the
  implementation, so this is not a compression demonstration; it is a proof-body
  rehearsal on a specimen we already understood. The compression economy is a
  separate axis (the widen move, on real code).

## Status

Measured 2026-09-05. The decider is built, teeth-verified (deterministic capture
of a real regression and the rare `/0` edge), and sealed as a record; the v3
draws are bounded-proven over the 2-op domain. This is move 1 of the reach-the-
jester plan — the first foothold on the proof body, converting "convergence" into
a small-scope theorem.
