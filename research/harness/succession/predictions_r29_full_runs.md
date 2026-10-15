# r29 continuation predictions: full runs for the two floor-clears

2026-10-15, written before the continuation launch, after the floor probes
resolved and before any layer past identity was attempted. Root stays
frozen at `3302eb8a`. The probes left layers 0-2 grown in each lineage
tree; the runner resumes at layer 3, which is the protocol working as
designed — a probe that clears the discriminator earns the rest of the
run, and pays for the first three layers only once.

- **P1 (haiku grows out).** `claude-haiku-5-5:high` grows all 21 layers.
  Its frontier sibling qualified at an earlier root, and the family's one
  recorded failure (r26) was a single-function defect, not a growth halt.
- **P2 (mistral halts late).** `mistral-large-3` does NOT reach 21/21;
  expected halt in the later band (crosscheck through reference, layers
  12-20), where modules get long and interfaces compound. It is the first
  family with no qualified sibling at any root, it runs without a
  reasoning-effort modifier, and its identity clear took 34 calls against
  haiku's 17. Being wrong here, like the probe's mistral call, would be
  the informative outcome.
- **P3 (no assembly-only refusals).** Whatever reaches assembly passes or
  fails nothing there that a layer did not already flag: specifically, an
  audit_deep defect is now refused at its own layer by the exchange
  fixture signed 2026-10-15, with retries in view. r26's failure mode —
  grow 21/21, then learn at assembly — should be structurally gone.
- **P4 (dollars).** haiku's full run costs under $1.50; mistral's under
  $8 if it completes, under $12 if it burns retries before halting.
  Measured per-side, cache priced where reported.
- **P5 (caching asymmetry persists).** haiku (google provider) keeps a
  cache-read share above half its prompt tokens; mistral (amazon) reports
  none, so its true cost IS its conservative cost.

If haiku grows out AND passes the full gate, held-out battery, and trial
sealing, the closure count at `3302eb8a` goes to 1 of 3 with a family that
is claude-adjacent but gateway-served. The count's independence argument
still wants gemini (r28, in flight) or mistral more.
