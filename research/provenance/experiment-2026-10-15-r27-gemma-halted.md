# r27 halted at identity: the first point on the capability floor

2026-10-15. Root `3302eb8a8f7ed73e368af387bb6e19bd29c60718b027c6493818c83744b7527b`,
frozen before the run. Lineage: `gemma` = `gemma-4-thinking@cborg`, the first
producer driven through the DOE Model Access Gateway, free tier, price $0.
**Halted at layer 02 (identity) after three attempts; 2 of 21 layers grown.
No trial claim; the closure count is untouched.**

Predictions were committed before the run in `predictions_r27.md`. All four
held.

## What happened

Core and recipe grew on attempt 1, in 28 seconds each — real modules, 2,543
and 1,671 bytes, written blind from the check text through an
OpenAI-compatible gateway by a free model. Then identity consumed three
attempts of 40 API calls each (the producer's turn cap), roughly 14 minutes
and 0.9M tokens per attempt, and never produced `IDENTITY_OK`:

```
attempt-failed x3: the gate never produced IDENTITY_OK
                   (turn cap or gate never passed)
halted
```

The run ledger shows exactly what the predictions required: three
`attempt-failed` records and a `halted`, no quota event, no silent pass
(P4). The plumbing never faulted — files read, files written, the gate run,
across every attempt (P1).

## The floor, located

Identity is the first layer whose check demands exact byte-level
serializations re-derived from prose. Both families that have ever qualified
(gpt-6-sol, claude sonnet) are frontier-tier; gemma-4 cleared the two layers
below that bar in under a minute and could not clear the first layer above
it in two million tokens of trying (P2). One free data point does not make a
curve, but it brackets the floor from below: the cheap tier of the MAG
roster (gpt-6-luna, haiku, nemotron) now has a concrete question to answer —
which of them clears identity?

## The cost envelope, now measured per side

Attempt 3 ran after the producer's accounting fix landed, so its usage
record is the first of the new shape (P3):

```json
{"calls": 40, "input_tokens": 858685, "output_tokens": 58132,
 "cached_input_tokens": 0, "tokens": 916817, "usd": 0.0,
 "usd_rates": {"input": 0.0, "output": 0.0, "cache_read": 0.0}}
```

Two readings from it. The producer's shape is 94% input, which is why the
old blended-midpoint pricing overstated metered runs — at gemini rates this
attempt would have cost $0.86, not the $2.06 the midpoint would have
reported. And `cached_input_tokens` is 0: the cborg serving stack reports no
prompt-cache detail, so on this provider the conservative path (cached
charged as fresh) is also the only path.

## What this does not show

Nothing about the spec: a producer below the floor failing to re-derive it
is the expected behaviour of a floor. And nothing yet about where the floor
IS — between gemma-4 and gpt-6-sol is a wide band, and the cheap MAG tier
exists to narrow it. The plumbing being proven at $0 was the run's actual
job, and it is done: the next lineage through the gateway pays only for its
own capability, not for discovering harness defects.
