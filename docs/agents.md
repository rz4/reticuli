# Working with agents

Agent output arrives faster than anyone can review it, and because it is
plausible, review is unreliable even when there is time for it. The
mechanism here does not review agent output. It verifies it.

The working rule is that the acceptance criteria are the asset and
implementations are candidates. Candidates are regenerated, compared, and
discarded by machinery the agent cannot influence.

## Agents as producers

A producer is any program that can regenerate a claim's implementation from
its pinned inputs. The contract runs through environment variables, an
output path in and a usage report out, so compilers, build systems, and
agents all qualify. The shipped agent producers run a bounded tool-use
loop: read the room's files, write a candidate, run the gate, and repeat
until it passes or the attempt budget is exhausted.

The prompt an agent receives is derived from the recipe rather than
hand-written for each task. It lists the files to create, the pinned inputs
to read, the gate command, and the rule that pinned files are never
modified. Setting `RETICULI_DRY_PROMPT=1` prints the exact prompt a claim
induces without calling an API.

Three isolation properties hold:

1. The producer sees only declared inputs, and the environment is scrubbed.
   Credentials and model selection are passed explicitly by the operator or
   not at all.
2. Producer guidance is excluded from the root and cannot decide
   acceptance.
3. The gate, the crosscheck, and the audit all run after the producer and
   apart from it. Passing the gate inside the room is necessary but not
   sufficient; the cold audit is what counts.

## What model capability does to a run

**Capability is discontinuous, and price does not predict it.** Models
cluster sharply around a claim's hardest criterion. Some pass it
immediately and cheaply, others never pass it at any attempt budget, and
neither price, vendor, nor generation reliably predicts which. Within a
single vendor family, an older generation at a higher tier can pass where a
newer generation at a lower tier fails. Probe each model against the
discriminating criterion, which costs cents, before funding a full run,
which costs dollars to tens of dollars.

**Failures must be classified before they are counted.** There are four
categories. A configuration failure means the request was refused and
retrying cannot help. A quota failure means throttling, which voids the
result. An infrastructure failure is a serving-path error worth retrying,
though a run whose every attempt died this way measured the provider rather
than the model. Capability is the residual, and it is never the assumption.
An unclassified failure log converges on a record of provider weather.

**Cost is accounted per token side and reconciled against the provider.**
Agent producers are extremely input-heavy, because the criteria are re-read
on every turn of the loop, so input tokens dominate by an order of
magnitude. Input, output, and cached-input prices differ by as much as 20×,
and a blended rate misstates real runs severalfold in either direction.
Record the cost per attempt in an append-only log at the moment it is
incurred — a record kept in a working directory will eventually be deleted
by the machinery that uses the directory — and treat the provider's own
accounting as authoritative.

## Agents as probe authors

The second role agents play is generating probes against populations of
implementations ([zeta internals](zeta.md)). Three constraints apply:

1. Every proposed probe must quote the specification text it targets,
   verbatim. The citation is checked mechanically before execution, and a
   probe that cannot cite one is refused without being run.
2. The agent's expected outcome is recorded and then ignored. The finding
   is whatever the population actually does, replayed by the standard
   machinery.
3. Only verified behavioral differences reach the queue.

One thing worth knowing before funding a sweep: against a saturated target,
where the criteria are already tight, probe generation rediscovers the
existing battery and finds nothing new. That result measures the target
rather than the generator. Yield appears against populations with real
variance. Measure recall against a hand-written battery as the control, and
treat new findings per unit cost as the figure of merit.

## Authority

Agents propose and machinery verifies. A human signature is the only
operation that turns any output into an obligation. Every artifact an agent
produced is reproducible by a party that trusts neither the agent nor its
operator.
