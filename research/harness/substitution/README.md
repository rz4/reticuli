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

## Stage 2 — with real rebuilds (not yet run)

Replace the hand-written `D`s with blind cross-family rebuilds of the config
parser (the `run_gen0.py` machinery) to show the divergence arises on its own,
and fold in soundness gaps A/B/C as prerequisites. Needs producer budget; a
keyholder decision (see the design note).
