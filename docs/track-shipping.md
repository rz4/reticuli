# I received, or ship, software

This track is for the reader on either end of a transfer: a claim arrived
and you must decide what to believe about it, or you are about to publish
one and want it to survive that same scrutiny. No agents are involved yet;
nothing here requires a model or an API key.

**What you can do at the end:** receive a claim and re-earn its verdicts
without trusting the sender; package your own work so a stranger can do the
same to you.

## The receiving journey

1. **[Quickstart](quickstart.md)** — ten minutes with a shipped example:
   verify it, audit it, break it on purpose and watch the audit refuse.
2. **[The process](process.md)**, sections 1–5 — what a claim is, what the
   root names, and why a verdict is accepted, rejected, or *incomplete*.
3. **[Receiving](receiving.md)** — the discipline in full: `verify` asks
   "is this the claim it names?"; `audit` asks "do its promises hold here,
   cold, from declared inputs only?"; records are the sender's evidence,
   to compare against, never to substitute for your own run.
4. **[Threat model](threat-model.md)** — who is trusted with what. Read it
   before you rely on a verdict; it is short, and it is mostly a list of
   who is *not* trusted.

## The shipping journey

1. **[Capturing](capturing.md)** — turning an existing project's build and
   checks into a claim: what to pin, what to leave out.
2. **[The process](process.md)**, sections 1–2 — the placement discipline:
   anything that should bind a future implementer goes in criteria or
   specification; anything that merely helped you does not.
3. **[Releasing](releasing.md)** — publishing so that verify-then-audit
   works from the received bytes alone.
4. When you are ready to claim more than "it passed here": the
   [three-machine test](process.md#the-three-machine-test), which is what
   your claim will face when someone takes it seriously.

## Where this track ends

If you find yourself wanting the tests to be *strong enough that an
implementation could be regrown from them* — because an agent writes your
code, or because you want proof the spec is sufficient — continue to
[reproducibility with agents](track-agents.md).
