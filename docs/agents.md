# Working with agents

Coding agents changed the economics of writing software without changing
the economics of trusting it. An agent can produce a plausible
implementation of almost anything in minutes; the reviewing human remains
the bottleneck, and plausibility is precisely what makes review hard.
Reticuli's response is an inversion that is useful anywhere agents write
code, whether or not this tool is in the loop:

**Stop treating the implementation as the asset. Make the acceptance
criteria the asset, pin them, and let implementations be regenerated,
compared, and discarded.**

Under that inversion an agent's output is never trusted and never needs to
be: it is a *candidate*, and candidates are judged by machinery the agent
cannot influence.

## Agents as producers

A producer is any program that can regenerate a claim's implementation from
its criteria. The contract is deliberately thin — a handful of environment
variables name the output to write and a file to report usage into — so a
compiler, a Makefile, or an agent all qualify. The agent-backed producers
shipped here drive a model in a bounded tool-use loop: read the room's
files, write the candidate, run the gate, repeat until it passes or the
attempt budget is spent.

What keeps this honest is the room, not the model:

- The agent sees **only declared inputs**. The environment is scrubbed;
  credentials and model choice are handed over explicitly by the operator
  or not at all.
- **Producer guidance is excluded from the identity.** Hints that help an
  agent along are allowed to exist, but they cannot decide acceptance and
  are not part of the root — a rebuild that needed the hint to pass would
  be measuring the hint.
- The gate, crosscheck, and audit run **after and apart from** the agent.
  A producer that games its own in-room gate still faces the cold audit.

## What to expect from models, measured

Running many models as producers against one fixed claim gives a
measurement most teams never get: which models can actually re-derive
software from its acceptance criteria. The results are not what price
sheets suggest, and three lessons generalize:

- **Capability is a staircase, not a line, and price does not order it.**
  Some inexpensive models clear criteria that models at seven times the
  price fail; within one vendor's family, a newer generation at one tier
  can fail where an older generation at a higher tier passes. Probe
  cheaply before committing to long runs: a three-stage probe against the
  first genuinely hard criterion costs cents and predicts whether a
  multi-hour run is worth starting.
- **Classify failures before believing them.** A refused request, a
  throttled connection, and a wrong answer are three different events. If
  the harness records them all as "the model failed," the measurement is
  corrupted silently. Capability should be the residual after
  configuration errors, quota, and infrastructure are excluded — never the
  assumption.
- **Account for cost per token side, from the provider's numbers.**
  Agent-driven producers are extremely input-heavy (the criteria are
  re-read on every loop turn), input and output prices differ severalfold,
  and cached input differs again. Keep the provider's own usage dashboard
  as the authority and reconcile your records against it; self-kept
  accounting that lives in working directories gets deleted by the
  machinery that uses it.

## Agents as pressure

The second role is newer: agents not as implementers but as **probe
authors** against a standing population of implementations. An agent is
given a slice of specification text and asked to propose inputs that the
text does not settle; every proposal must cite the text it targets,
verbatim, and the citation is checked mechanically before anything
executes. The agent's *expectation* is recorded but decides nothing — the
finding is whatever the population actually does, replayed and classified
by the same machinery as every hand-written probe.

This division survives low-quality agents by construction. A proposal that
cannot cite its clause is refused unexecuted. A proposal that executes but
splits nothing is an agreement, cheap to store. Only a verified behavioral
difference reaches the queue — and the queue is where a human decides.
Measured in practice: a small, inexpensive model rediscovered an entire
hand-written probe battery from specification text alone, and against a
population of three independently authored implementations found genuine
divergences the hand-written battery had missed, for about a cent per
sweep.

## The one rule

Everything above reduces to a single invariant, and it is worth stating
plainly because it is the part that transfers to any agent workflow:

**Agents propose; machinery verifies; people authorize.** No agent output
becomes an obligation — a criterion, a specification clause, a release —
except through a human signature, and everything an agent produced on the
way is reproducible by someone who trusts none of it.
