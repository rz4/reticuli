# r32 predictions: the grok family's first real probe, and the gpt ladder

2026-10-15, written before the launch. Root frozen at `3302eb8a`. Two floor
probes (`--stop-after 3`, fixed 40-turn budget, quota and infrastructure
void):

| lineage | model | question |
|---|---|---|
| grok-amazon | grok-4.6@amazon | the grok family's first MEASURABLE probe — the microsoft path produced only a modifier refusal, a throttle, and 403s |
| sol56 | gpt-5.6-sol:high@microsoft | the gpt generation ladder at fixed tier, mirroring gemini's |

Confounds declared now: grok-4.6 serves no effort modifier, so it runs at
default against a mostly-`:high` table (the same confound the old geminis
carried). And codex — the qualified gpt-6-sol — ran through its own CLI,
not the gateway, so the gpt ladder varies serving path as well as
generation.

- **P1 (grok clears identity).** Called with low confidence, mostly on
  tier: grok-4.6 is priced as a frontier model ($2.20/$6.60), and every
  frontier-priced producer measured so far except gemini-flash sits above
  the identity rung. A failure puts a fifth family below the floor and
  strengthens the family-shaped reading; either answer finally gives the
  grok column a value.
- **P2 (the gpt ladder mirrors gemini's).** gpt-5.6-sol FAILS identity.
  gemini crossed the floor between generations 2.5 and 3.1 at fixed tier;
  if gpt crossed it between 5.6 and 6, "the floor is generational within a
  family" replicates and becomes a pattern rather than an observation. If
  sol56 clears, the gpt family was above the floor a generation earlier
  than gemini, which is also informative: it would say the floor's
  generational crossing point is family-specific.
- **P3 (dollars).** Both probes together under $6. sol56 is the priciest
  probe yet ($4/$20); a three-attempt identity failure at the turn cap is
  the expensive outcome and is bounded near $5 alone.
- **P4 (integrity).** Any configuration refusal, throttle, or serving-path
  failure voids the probe rather than counting against the family — the
  rule that kept three bogus results out of the table today.
