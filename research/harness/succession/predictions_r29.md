# r29 predictions: bracketing the floor with the cheap tier

2026-10-15, written before the run. Root frozen at `3302eb8a`. Five lineages
through the DOE gateway, all with `--stop-after 3`.

## The design

r27 located the floor from below: gemma-4 grew core and recipe in 28 seconds
each and then failed identity three times at the turn cap. Identity is the
first layer whose check demands exact byte-level serializations re-derived
from prose, so "clears identity" is the cheapest sharp question that
separates a producer that might qualify from one that cannot.

So this is not five succession runs. It is five **floor probes**: layers 0-2
only (core, recipe, identity), the same three gemma-4 faced, under the same
40-turn producer cap both qualifying families had. The cap is held fixed
deliberately — raising it for a weaker model would measure patience, not
capability.

| lineage | model | quoted $/Mtok in,out |
|---|---|---|
| nemotron | nemotron-super-3@amazon | 0.15, 0.65 |
| oss | gpt-oss-120b@amazon | 0.15, 0.60 |
| luna | gpt-6-luna:high@microsoft | 0.10, 0.50 |
| haiku | claude-haiku-5-5:high@google | 0.10, 0.50 |
| mistral | mistral-large-3@amazon | 0.50, 1.50 |

## Predictions

- **P1 (the split).** The tier splits rather than passing or failing as a
  block. Predicted to clear identity: `luna` and `haiku` — small members of
  families whose frontier siblings have both qualified, both carrying
  reasoning effort at `:high`. Predicted to fail: `nemotron` and `oss`.
  `mistral` is called as a genuine coin-flip and is the one I would most
  like to be wrong about.
- **P2 (core and recipe are below the floor for everyone).** All five grow
  layers 0 and 1. gemma-4 did it in 28 seconds; nothing in this tier is
  weaker than gemma-4.
- **P3 (cost).** All five probes together come in under $5 as measured by
  the per-side envelope. A failing probe costs MORE than a passing one —
  three attempts at the turn cap versus one short success — so the bill is
  dominated by the failures.
- **P4 (no quota confound).** No lineage stops on a `quota` event. This one
  is a measurement-integrity check, not a claim about the models: the
  harness treats "rate limit" as a clean stop, and a quota stop misread as
  a capability failure would silently corrupt the floor. Any quota event
  voids that lineage's result rather than counting as a failure.

## What a result means

Clearing identity is necessary, not sufficient. Later layers (crosscheck,
attest, the composed audit at 18) are harder in different ways, and r26
showed a frontier family growing all 21 layers and still failing the gate.
A lineage that clears identity here earns a full run, nothing more.
