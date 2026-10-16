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

The prompt an agent receives is derived from the recipe, not hand-written
per task: the files to create, the pinned inputs to read, the gate command,
and the rule that pinned files are never modified.
`RETICULI_DRY_PROMPT=1` prints the exact prompt any claim induces without
calling an API; [the session](session.md#what-an-agent-producer-is-told)
shows one captured.

Isolation properties:

1. The producer sees only declared inputs. The environment is scrubbed.
   Credentials and model selection are passed explicitly by the operator
   or not at all.
2. Producer guidance is excluded from the root and cannot decide
   acceptance.
3. Gate, crosscheck, and audit run after and apart from the producer. An
   in-room gate pass is necessary, not sufficient; the cold audit is
   authoritative.

## Model capability: operating constraints

1. **Capability is discontinuous and price does not predict it.** Models
   cluster sharply around a claim's hardest criterion: some pass it
   immediately at low cost, others never pass it at any attempt budget,
   and neither price, vendor, nor generation reliably predicts which.
   Within one vendor family, an older generation at a higher tier can pass
   where a newer generation at a lower tier fails. Probe each model
   against the discriminating criterion (cents) before funding a full run
   (dollars to tens of dollars).
2. **Failures must be classified before they are counted.** Four
   categories: configuration (the request was refused; retry cannot
   help), quota (throttled; voids the result), infrastructure
   (serving-path error; retry, but a run whose every attempt died here
   measured the provider, not the model), capability (the residual).
   Capability is never the assumption. An unclassified failure log
   converges to a record of provider weather.
3. **Cost accounting: per token side, reconciled against the provider.**
   Agent producers are extremely input-heavy: the criteria are re-read on
   every loop turn, so input tokens dominate by an order of magnitude.
   Input, output, and cached-input prices differ by up to 20×; a blended
   rate misstates real runs severalfold in either direction. Record cost
   per attempt in an append-only log at the moment it is incurred — a
   record kept in a working directory will eventually be deleted by the
   machinery that uses the directory — and treat the provider's own
   accounting as authoritative.

## Agents as probe authors

Second role: agents generate probes against populations of
implementations ([zeta internals](zeta.md)). Constraints:

1. Every proposed probe must cite the specification text it targets,
   verbatim. The citation is checked mechanically before execution. A
   probe that cannot cite is refused unexecuted.
2. The agent's expected outcome is recorded and ignored. The finding is
   the population's observed behavior, replayed by the standard machinery.
3. Only verified behavioral differences reach the queue.

Operating note: against a saturated target (criteria already tight), probe
generation rediscovers the existing battery and finds nothing new — a
result that measures the target, not the generator. Yield appears against
populations with real variance. Measure recall against a hand-written
battery as the control, and treat new findings per unit cost as the figure
of merit.

## Authority

Agents propose. Machinery verifies. A human signature is the only
operation that converts any output into an obligation. Every artifact an
agent produced is reproducible by a party that trusts neither the agent
nor its operator.
