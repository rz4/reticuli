# r28 halted at identity: the floor is family-shaped, at seven times the price

2026-10-15. Root `3302eb8a`, frozen before the run. Lineage: `gemini` =
`gemini-3.8-flash:high@google`, the first paid MAG lineage. **Halted at
layer 02 (identity) after three attempts; 2 of 21 layers grown. No trial
claim; the closure count is untouched.** Predictions in `predictions_r28.md`.

## Predictions, resolved

- **P1 (clears identity)** — **falsified.** Three 40-turn attempts, no
  `IDENTITY_OK`. Same wall as gemma-4, gpt-oss-120b, nemotron-super-3 and
  gpt-6-luna.
- **P2 (21/21)** — falsified with P1. It also needed three attempts at
  RECIPE, a layer every other producer in two days cleared on its first —
  diagnosed mid-run as a possible output-truncation defect and ruled out by
  a direct probe (tool calls emit fine), so the struggle was the model's.
- **P3 (audit_deep steering)** — moot; never reached layer 18.
- **P4 (under $10)** — held. Observed $0.97; a bounded-under-3x correction
  for wiped failed attempts keeps the true figure under $3.
- **P5 (google reports caching)** — **held, strongly.** 1.7M of 2.3M prompt
  tokens served from cache (74%), priced at $0.07/Mtok. Without the
  per-side fix landed this morning, this run would have been booked at
  roughly 4x its true cost.

## What the halt means

The surprising comparison is not gemini against the cheap tier — it is
gemini against haiku. `claude-haiku-5-5:high` costs $0.10/$0.50 per Mtok
and cleared identity in 17 calls for $0.04. `gemini-3.8-flash:high` costs
7x more and failed in 120 calls. Price does not order the floor; family
does. This is now measured three ways in one day (haiku over luna at equal
price, mistral over nemotron at 3x, haiku over gemini at a 7th the price),
and it is the empirical case for heterogeneous reconstruction populations
over depth in any one family.

For the third-family goal, the consequences are concrete: the gemini
family's next candidate is `gemini-4-argon` ($2/$10, the `argon` lineage,
already registered), and `mistral-large-3` — in flight past identity as
this is written — is currently the best open hope for a family with no
previously qualified sibling.

## Measurement notes

Per-layer observed spend (last attempt per layer; wiped attempts bounded
under 3x): core $0.25, recipe $0.50, identity $0.22. The identity attempt
spent 694,091 cached + 177,522 fresh input tokens against 11,234 output —
the producer re-reads everything and writes almost nothing when it is
stuck, so a stuck layer's cost signature (input:output above 60:1) is
distinguishable from a productive one's (~15:1) in the ledger alone. That
ratio may be useful as an early-abort signal if probe budgets ever matter
more than they do at these prices.
