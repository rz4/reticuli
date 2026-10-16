# Track 1: receive or ship software

Scope: one party publishes a claim; another receives it and decides what
to believe. No agents, no models, no API keys.

Outcome: receive a claim and re-earn its verdicts without trusting the
sender; publish work that survives the same procedure.

## Receiving

1. [Quickstart](quickstart.md) — a shipped example: verify it, audit it,
   corrupt it, watch the audit refuse.
2. [The process](process.md), §1–5 — the claim structure, the root, the
   three-valued verdict.
3. [Receiving](receiving.md) — `ret verify`: is this the claim it names?
   `ret audit`: do its promises hold here, cold, from declared inputs
   only? Sender records are comparison evidence, not substitutes.
4. [Threat model](threat-model.md) — the trust boundaries. Read before
   relying on any verdict.

## Shipping

1. [Capturing](capturing.md) — converting an existing project's build and
   checks into a claim.
2. [The process](process.md), §1–2 — the placement rule: what binds a
   future implementer is pinned; what helped the current one is not.
3. [Releasing](releasing.md) — publishing such that verify-then-audit
   works from received bytes alone.
4. [The three-machine test](process.md#the-three-machine-test) — the
   procedure a published claim faces.

Next: tests strong enough to regrow an implementation from —
[track 2](track-agents.md).
