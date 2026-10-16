# Track 2: reproducibility in agent work

Scope: code written by models — local coding agents, gateway-served
producers, CI over machine-written changes. The question answered: what
was verified before the merge.

Outcome: run any agent as a producer judged by machinery it cannot
influence; probe model capability before paying for it; keep cost and
failure accounting that survives contact with providers; review
machine-written PRs by holding the criteria to account.

## Order

1. [Working with agents](agents.md) — producers, rooms, the scrub; the
   measured capability and cost constraints.
2. [Writing criteria](criteria.md) — reproducibility is bounded by
   criteria sufficiency. Four rules, each from a measured failure.
3. [Producing](producers.md) — the producer contract: environment
   protocol, usage reporting, adapters.
4. [GitHub and CI](github.md) — what a green check establishes; the three
   diff classes and their review procedures.

## Constraints to internalize first

- Reconstruction is a capability question before a workflow question. Some
  models cannot rebuild from criteria at any price; price does not predict
  which. Probe (cents) before running (dollars).
- A failure is unclassified until proven otherwise. Throttles, refused
  requests, serving-path errors, and wrong answers belong in separate
  columns; mixing them turns a capability table into a log of provider
  outages.

Next: reconstruction as a measurement of the specification —
[track 3](track-specification.md).
