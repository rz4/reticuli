# Proposal — the chain build is incremental: a doubling bounds the cost

*Staged 2026-10-10, from r22's envelope refusal — the keyholder asked
whether an algorithmic pin could be laid; this is it, measured to the
exponent. A criteria edit in the authoring layer; a root move; staged
for signature.*

## The finding

r22 (claude) timed out at the declared gate window (3600 s) with every
reached criterion green; the original tree's whole gate runs in 73 s at
the same boundary, r21 (codex) fit with ~49× slack, and r22's micro
primitives are near-flat — so the heat is scale-dependent. The scaling
probe (research/harness/corpus/scaling_probe.py) built self-claim-shaped
chains with each realization's own pack:

    K=4      K=8      K=16     doubling ratio 8→16
    gen0   0.21 s   0.52 s    1.83 s     ×3.5
    r21    0.26 s   0.52 s    1.08 s     ×2.1
    r22    0.33 s   0.90 s   86.01 s     ×95

The 2^K model predicts r22 at K=12 ≈ 5.4 s; measured: 5.39 s. r22's
chain build is EXPONENTIAL in depth — it re-visits each ancestor once
per path that reaches it (the store's ancestor symlinks walked rather
than resolved once), the TRAVERSAL sibling of the copytree disk seam the
compactness pin closed on the byte axis. On the twenty-layer self-claim
chain inside self_check, that is the 65-minute gate.

## Why this is pinnable where speed is not

Wall-clock is host-dependent; a SAME-HOST DOUBLING RATIO cancels the
host and measures the algorithm — the growth rate is a property of the
code, exactly as physical copy-count was. Precedent on both sides: the
compactness pin ("each dependency's bytes appear O(1) times") and the
declared gate window (which held, and is the reason r22 was refused —
this pin names WHAT it refused and steers the next draw at the layer,
early, instead of sixty-five minutes into identity).

## What to pin

An authoring_check fixture: build the self-claim-shaped chain at K=8 and
K=16 with the implementation's own pack (uniform patterns, carried
modules, ancestor symlinks — the real chain's shape) and require
t(16)/t(8) ≤ 10. Conforming implementations measure 2.1–3.5 with the
inherent file growth included; the exponential measures ~95. The bound
is a growth rate, never a speed: a slow-but-linear implementation on a
slow host passes; a fast exponential one fails. Criterion cost ~2.5 s
for a conforming implementation.

## Measured before staging

The probe IS the fixture logic: gen0 and r21 pass the bound with ≥3×
margin; r22 exceeds it by ~10×; the K=12 interpolation confirms the
exponent rather than a constant. Flakiness margin: the pass band and the
violation differ by an order of magnitude on a ratio that cancels load.

## Status

STAGED for the keyholder. A root move (authoring); landing regrows
trial 2 at the new root. Count unaffected until signed (1 of 3 stands).
