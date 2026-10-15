# r28 predictions: the first paid MAG lineage (gemini)

2026-10-15, written before the run. Root frozen at `3302eb8a`. Lineage:
`gemini` = `gemini-3.8-flash:high@google` through the DOE gateway, quoted at
$0.75 input / $3.75 output / $0.07 cache-read per million tokens. This is
the first run whose cost envelope carries metered dollars, and the first
candidate for a third qualifying family.

What the run can and cannot settle: growth is this harness; the identity
test (full gate, held-out tests, trial sealing) runs afterward as the same
judge steps r25/r26 used. A prediction about sealing is a prediction about
both stages.

- **P1 (the floor, from above).** gemini-3.8-flash clears the identity
  layer within its three attempts — the layer that halted gemma-4 at the
  turn cap three times. If this holds, the capability floor sits between
  gemma-4 and flash-tier gemini, a much narrower band than "below gpt-6-sol".
- **P2 (growth).** All 21 layers grow. Weakest prediction here: r26 showed
  a frontier family growing 21/21 while still failing the gate, so growth
  alone is expected of anything that clears identity.
- **P3 (the audit_deep gene).** If the tree reaches assembly, it passes the
  full gate including `self_check`'s composed-audit count. The just-signed
  layer-local fixture in `exchange_check` means a producer that writes a
  non-memoising or shape-dropping `audit_deep` is refused AT LAYER 18 and
  gets up to two more attempts with the refusal in view — the steering that
  r26's claude never received. A layer-18 retry that then converges would be
  the fixture earning its signature.
- **P4 (dollars).** The whole growth run costs under $10 as measured by the
  per-side envelope. Estimate ~$3–6: easy layers at gemma-like token counts,
  a few hard layers near the cap. Worst case (every layer at the cap, three
  attempts) is bounded near $50 and is not predicted.
- **P5 (caching).** The google provider reports nonzero `cached_input_tokens`
  — the table quotes a cache-read rate — so the true cost lands below the
  all-fresh estimate. Falsified if, like cborg, the serving stack never
  reports cache detail.

If growth completes and the gate passes, the trial seals and the closure
count at `3302eb8a` goes to 1 of 3 — with a family neither codex nor claude,
which no previous count ever had.
