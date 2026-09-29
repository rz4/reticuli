# Substitution demonstrator

*Research tooling — not normative, not pinned.*

Tests the property the quirkcalc contraction curve does not: that a dependency
which passes its own gate is safe to **substitute under a consumer**
(consumer-relative sufficiency). Plan and rationale:
[`research/design/substitution-demonstrator.md`](../../design/substitution-demonstrator.md).

## Stage 1 — the core finding, no producers

    python3 research/harness/substitution/demo.py

A config parser `D` with a deliberately partial boundary `C_0` (pins only
non-numeric, single-key behavior — silent about duplicate keys and numeric
coercion), three hand-written implementations that all pass `C_0` but diverge on
that open surface (`parsers/`), and a consumer `P` whose correctness depends on
it (`consume` doubles a duplicate, numeric `port`). Result:

- all three dependencies pass `C_0`, but only one keeps `P` working;
- the two gate-passing-but-breaking dependencies expose the obligations `P`
  relied on silently (coercion, last-wins);
- closing those to `C_1` leaves only dependencies that keep `P` working —
  substitution becomes safe.

So a gate-passing dependency is *not* thereby substitutable; consumer-relative
sufficiency is a distinct, stronger property the ratchet has to reach.

## Stage 2 — with real rebuilds (run 2026-09-28)

    python3 research/harness/substitution/stage2/run_stage2.py            # round 1
    python3 research/harness/substitution/stage2/run_stage2.py --round2   # the ratchet

The hand-written `D`s replaced by blind cross-family rebuilds (3 codex, 3
Claude Code) of a sealed `kvparse` claim, judged by auditing a sealed
consumer claim with each reconstruction substituted for its generated
parser. Result: 6/6 pass `C_0`, 6/6 distinct bytes, **0/6 keep the consumer
working** — every model in both families kept values as strings, so the
consumer's `port * 2` became string repetition. From the tightened `C_1`:
6/6 keep the consumer working. The full record:
[`research/provenance/rebuild-2026-09-28-substitution-stage2.md`](../../provenance/rebuild-2026-09-28-substitution-stage2.md).
