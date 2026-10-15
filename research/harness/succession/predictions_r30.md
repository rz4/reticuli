# r30 predictions: argon, the gemini family's frontier candidate

2026-10-15, written before the launch. Root frozen at `3302eb8a`. Lineage:
`argon` = `gemini-4-argon:high@google`, $2/$10/$0.10 per Mtok — the most
expensive producer tried so far. Launched as a gated continuation: the
floor probe (layers 0-2) runs first, and the full run proceeds in the same
launch ONLY if identity is grown. A halt at identity spends probe money
only.

Context the predictions answer to: gemini-3.8-flash (r28) failed identity
at 7x haiku's price, and struggled at recipe where every other family
cruised. Either the flash tier is below a floor the frontier tier clears,
or the gemini family's trouble with this criterion is not about tier.

- **P1 (identity).** argon clears identity within three attempts. Called
  with moderate confidence: frontier tiers of two families (gpt-6-sol,
  sonnet) sit comfortably above this criterion, and argon is gemini's
  frontier. A failure here would put an entire family below the floor at
  every price point tried, which would be the single most surprising
  measurement of the day.
- **P2 (growth).** If identity clears, all 21 layers grow.
- **P3 (dollars).** Probe under $3; full run under $25 if it goes the
  distance. The model's quoted rates are 2.7x flash's.
- **P4 (caching).** The google provider keeps its cache behaviour:
  above half the prompt tokens served at the $0.10 cache-read rate.
- **P5 (recipe tell).** Watch the recipe layer: flash needed three
  attempts there. If argon also stumbles on recipe, that is a
  family-level signature of difficulty with this harness's room shape,
  not a tier effect — informative either way it resolves.
