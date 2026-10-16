# Working with agents

Premise: agent output volume exceeds human review capacity, and
plausibility makes review unreliable. The mechanism here does not review
agent output. It verifies it.

Rule: **the acceptance criteria are the asset; implementations are
candidates.** Candidates are regenerated, compared, and discarded by
machinery the agent cannot influence.

## Agents as producers

A producer is any program that regenerates a claim's implementation from
its pinned inputs. The contract is environment-variable based (output path
in, usage report out), so compilers, build systems, and agents all
qualify. The shipped agent producers run a bounded tool-use loop: read
room files, write candidate, run gate, repeat until pass or attempt budget
exhausted.

Isolation properties:

1. The producer sees only declared inputs. The environment is scrubbed.
   Credentials and model selection are passed explicitly by the operator
   or not at all.
2. Producer guidance is excluded from the root and cannot decide
   acceptance.
3. Gate, crosscheck, and audit run after and apart from the producer. An
   in-room gate pass is necessary, not sufficient; the cold audit is
   authoritative.

## Model capability: measured constraints

Results from running 16 producer configurations against one fixed claim
(2026-10; records in `research/`):

1. **Capability is discontinuous and price does not predict it.** Against
   the first discriminating criterion: models at $0.10–0.11/Mtok passed
   where models at $0.75 and $1.25/Mtok failed. Within one vendor family,
   an older generation at a higher tier passed where a newer generation at
   a lower tier failed. Probe each model against the discriminating
   criterion (cost: cents) before funding a full run (cost: dollars to
   tens of dollars).
2. **Failures must be classified before they are counted.** Four
   categories: configuration (request refused; retry cannot help), quota
   (throttled; voids the result), infrastructure (serving path error;
   retry, but a lineage whose every attempt died here measured the
   provider, not the model), capability (the residual). In the measured
   campaign, 5 of 9 apparent capability failures were reclassified on
   inspection: one gateway misconfiguration, one throttle with quota
   remaining, two serving-path outages, one harness defect. An
   unclassified failure log converges to a record of provider weather.
3. **Cost accounting: per token side, reconciled against the provider.**
   Agent producers are input-heavy (criteria re-read every turn; measured
   94% input). Input, output, and cached-input prices differ by up to 20×.
   Blended-rate accounting overstated a measured run 2.2×–5.4×.
   Self-kept usage records stored in working directories were deleted by
   the harness that used them (measured undercount: 7.3×); store cost
   records in append-only logs at the moment of capture, and treat the
   provider's dashboard as authoritative.

## Agents as probe authors

Second role: agents generate probes against populations of
implementations ([zeta internals](zeta.md)). Constraints:

1. Every proposed probe must cite the specification text it targets,
   verbatim. The citation is checked mechanically before execution. A
   probe that cannot cite is refused unexecuted.
2. The agent's expected outcome is recorded and ignored. The finding is
   the population's observed behavior, replayed by the standard machinery.
3. Only verified behavioral differences reach the queue.

Measured (2026-10): a $0.10/Mtok model, given specification text only,
reproduced 100% of a hand-written probe battery's findings on one target
(saturated; 0 new) and on a second target (three independently authored
implementations of an external language) reproduced 62.5% and found 2
divergences the hand-written battery had missed. Cost per sweep: ~$0.01.

## Authority

Agents propose. Machinery verifies. A human signature is the only
operation that converts any output into an obligation. Every artifact an
agent produced is reproducible by a party that trusts neither the agent
nor its operator.
