# The final bundle — the last clicks between here and a quiet map

*2026-10-03, staged for the keyholder. The tier-1 triage
(`experiment-2026-10-03-tier1-triage.md`) found zero new pins owed from
the surface worklist: the measurable distance to a quiet map is exactly
the clicks below plus one declaring sentence. Each item names its edit,
what it buys, and its evidence. Signing the bundle is one decision; the
transition executes as one root move with the usual ritual.*

## The clicks, in value order

**1. The scrub canary (was G).** `kernel_check` gains a rebuild whose
producer script writes its environment to a file; assert a canary
variable planted in the caller's environment is ABSENT in the room while
a `producer_env`-passed variable is PRESENT. Buys: no conforming kernel
can leak an inherited credential to a producer again — the leaked
ANTHROPIC key, witnessed by use, becomes impossible rather than unlucky.

**2. Rebuild's surface reconciled (was C).** Two edits, one truth:
`spec/kernel-api.md` adopts `guidance` and `producer_env` as `rebuild`'s
remaining keywords (today the spec names neither, the original carries
both, the checks pin nothing — the measured three-way disagreement);
`kernel_check` pins them behaviorally — a guided claim rebuilt with
`guidance=False` must not expose the hint in the room (the canary
producer reports what it saw), and `producer_env` is the only way a
caller-supplied variable arrives. Buys: external drivers become portable
across conforming kernels; the five-way `rebuild` signature spread
converges the way `pack`'s did.

**3. The declared timeout's direction (was B, absorbing I).**
`run_check` gains the case the succession paid an hour to learn: a gate
sleeping a few seconds under a claim-declared `gate_timeout` generous
enough must PASS even where an implementation's default is lower — the
declaration is the ceiling for that claim's gates, not a suggestion the
host may undercut. Buys: a conforming tool can always audit the
repository that declares its own window; the 60-second `min()` kernel
becomes non-conforming. (The audit-diet click I is absorbed: the same
case carries nested inputs, so "audits small fixtures" stops standing in
for "audits this repository" without adding a slow gate to every run.)

**4. The verdict vocabulary (was H).** `surface_check` pins the mapping
`spec/verification.md` already writes down: a failed gate reports
`failed`, never `broken` — the identity-damage word — on a fixture whose
gate fails but whose bytes verify. Buys: verdict words stay trustworthy
across implementations; the claude-g1 misuse becomes non-conforming.

**5. Reference joins the chain (was E).** `scripts/selfclaim.py` gains
the twentieth layer — `reference.py`, judged by `vectors_check` through a
wrapper gate, exactly as the succession harness already builds it. Buys:
the decomposition covers the claim's full generated surface; the
self_check lockfile gains the layer's root.

**6. Reuse becomes a promise (verdict-cache Part 2).** `measure_check`
pins the cache's honesty contract: a reused verdict reports `reused`
(never `earned`) and echoes its trust policy; a changed byte under the
same key re-earns. Buys: the scaling machinery's honesty stops being a
convenience of this implementation and becomes something every
conforming tool must keep.

**7. The declaring sentence.** `spec/layers.md` states what the triage
measured: intra-package seams — names generated modules consume from one
another — are deliberate freedom; sub-layer internals are rebuilt as a
set, and only the surface the pinned boundary consumes is contract.
One sentence; 197 measured seams become declared, not dangling.

## What was scrutinized out

- **Click I as a separate criterion** — absorbed into 3; a dedicated
  repository-shaped audit fixture would add minutes to every gate run
  for coverage the timeout-direction case already provides.
- **Any pin from the 268-seam worklist** — the triage found the residue
  empty; the worklist is an audit result, not a backlog.

## After the bundle

By the project's own instruments, nothing remains that anything stands
on. What follows is the endgame, in order: the clean-room findings
(whatever the stranger simulation surfaced) folded into `requires`/docs;
the keyholder's ceremony — paid-ladder blind reproduction, signature,
the fixpoint tag; and the open door.
