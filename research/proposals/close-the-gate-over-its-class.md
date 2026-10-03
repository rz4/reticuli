# Close the gate over its own equivalence class

*2026-09-29, proposal — held for the keyholder. Every change here moves the
root; nothing is applied. Evidence: the succession run
(`research/harness/succession/`, record in `research/provenance/`).*

## The finding this answers

The succession run grew a complete generation-1 implementation on regrown
ancestry (codex lineage: 20 layers, 37 modules, 4,118 lines against the
original's 10,856). Judged three ways: the held-out `tests/` battery
passes **102 of 102** environment-valid tests — behaviorally, the regrown
tool is the tool. The repository root recomputes unchanged. And yet
`REPO_OK` refuses — not because the implementation is wrong, but because
**the gate's own pinned machinery consumes names the criteria never pin**.
The gate is not closed over the equivalence class it names: a conforming
member can fail it. Every specimen found:

1. **Pinned selfclaim.py → unpinned pack API.** `scripts/selfclaim.py`
   (pinned) calls `pack(..., gate_output=..., component=..., envelope=...,
   claim_format=...)`. `authoring_check` exercises `pack` positionally
   only, so a conforming pack has different keyword names and none of
   those three features. The pinned surface leans on API only convention
   keeps alive.
2. **Declared gate_timeout cannot do its job.** The recipe declares
   `gate_timeout = 1800` (identity-bearing, added 2026-09-28 precisely so
   the repository's own audit fits). The default timeout is declared
   implementation-defined, and the regrown kernel chose 60 seconds with a
   `min(env, declared)` combiner — conforming, and structurally unable to
   honor a claim that *raises* its ceiling. The declared freedom contains
   the one behavior the standing invitation depends on.
3. **Spec, check, and original disagree on `rebuild`'s surface.**
   `spec/kernel-api.md` names `produce_from` and `input_from` as the
   keywords; the original also carries `guidance` and `producer_env`
   (undocumented); the checks pin neither. The regrown kernel implemented
   exactly the spec — and every external caller written against the
   original breaks on it.
4. **Sub-layer seams ride on privates.** Original `identity.py` calls
   `recipe._inputs(recipe, claimdir)`; original `recipe.py` reads
   `core.KINDS`. The sub-layer checks pin outward behavior only, so
   original modules cannot stand on independently regrown lowers (both
   lineages refused within two layers until the harness threaded regrown
   ancestry throughout).
5. **The layer decomposition omits reference.py.** `scripts/selfclaim.py`
   names nineteen layers; the repository claim generates 37 modules; the
   difference is `reference.py`, judged by `vectors_check` but belonging
   to no layer.
6. **The producer scrub's drop-list is unpinned — and it leaked a
   credential.** The original scrub drops inherited vendor keys so a
   subscription CLI producer never sees them; the claude-lineage kernel's
   conforming scrub passed `ANTHROPIC_API_KEY` through to the producer,
   which promptly billed a metered key. The scrub exists to prevent
   exactly this; no check pins what it must drop (a canary-variable case
   would). **Confirmed by use 2026-09-30**: the r2 rerun's regrown claude
   kernel could not drive the external `claude` CLI producer at all — its
   scrub stripped what the CLI needs to authenticate ("Not logged in"),
   and with no `producer_env` pass-through (specimen 3) there was no way
   to restore it. The scrub's keep-list being unpinned is not only a leak
   risk; it can make a regrown tool unable to operate a credentialed
   producer.
7. **The verdict vocabulary is normative but unenforced.**
   `spec/verification.md` defines what each verdict means; the
   claude-lineage tool reports a *failed gate* as `broken` — the word
   the spec reserves for identity damage — and no check refuses it.
8. **Self-hosted operability is not implied by conformance.** The
   codex-lineage tool re-earned `REPO_OK` on the repository through its
   own audit (its timeout knob raised) and drove a blind generation-2
   rebuild. The claude-lineage tool verifies the repository and refuses
   tampering, but its repository audit dies in seconds, and its rebuild
   refuses EVERY real producer session — its tamper watch reads the
   residue a working producer leaves in the room (the gate output it is
   told to earn, bytecode caches from the gate importing modules) as
   "pinned bytes rewritten" — while still passing the criteria's own
   rebuild cases, whose toy producers leave no residue. Succession held
   for one family and broke for the other, and the criteria permit both.

## The proposed clicks (each a root move, each separately acceptable)

- **A. Pin what selfclaim consumes.** `authoring_check` gains cases that
  call `pack` with the keyword names and the three features selfclaim
  uses (component layering, envelope, claim_format): the gate's own
  scripts define a minimum API contract, so pin exactly that.
- **B. Pin the timeout's direction.** A declared `gate_timeout` must be
  honored as the ceiling for that claim's gates (a check with a slow gate
  and a large declared timeout must pass). Keep the *default* free;
  pin that declaration wins.
- **C. Reconcile `rebuild`'s surface.** Either the spec adopts
  `guidance`/`producer_env` and `kernel_check` pins them by name, or the
  original sheds them. Recommendation: adopt and pin — blind rebuilds
  (`guidance=False`) are load-bearing in the research harnesses and the
  producer-credential channel is the documented pass-through.
- **D. Pin the sub-layer seams, or fuse the rooms.** Two options:
  each sub-layer check pins the private names the next original module
  consumes (small, explicit list), or the kernel chain is declared
  rebuildable only as one room. Recommendation: pin the seams — the
  succession showed regrown-on-regrown works, so the seams are real
  interfaces; name them.
- **E. Give reference.py a layer.** Add it to `scripts/selfclaim.py`'s
  chain (judged by `vectors_check`), so the decomposition covers the
  claim's full generated surface.
- **G. Pin the scrub's obligation.** A producer step must not see any
  inherited variable off the keep-list: plant a canary in the caller's
  environment, have the producer echo its environment, assert absence.
  Small check, closes a real leak class.
- **H. Enforce the verdict vocabulary.** A failed gate must not be
  reported with an identity-damage word; pin the verdict-to-cause
  mapping the spec already writes down.
- **I. Pin the audit's own diet.** The audit of the repository claim IS
  the standing invitation's mechanism; a criterion should exercise
  audit against a claim with the repository's structural features
  (nested inputs, large gate, declared timeout) so "can audit small
  fixtures" stops standing in for "can audit this repository".
- **J. Pin rebuild against a realistic producer.** A rebuild case whose
  producer runs the gate in-room — creating the gate output and
  bytecode residue, as every real producer does — must be accepted; the
  tamper watch's scope is the recipe and the declared inputs, nothing
  more.
- **F. The closure check (the general repair) — BUILT 2026-10-03, staged
  for promotion.** `research/harness/closure/closure_check.py` walks every
  pinned file's imports, attribute uses, and call keywords into the
  generated package and asserts the owning layer's check exercises each.
  Validated against history: it flags the exact pack seam at the
  pre-click-A boundary and confirms it closed at today's — and it found
  four further latent gaps in seconds (pinned criteria consume
  `kernel.MANIFEST`, `kernel.ledger`, `kernel.RECIPE`, unexercised by
  kernel_check; every regrown kernel so far happens to carry them, i.e.
  the prior saved us, the reliance this project refuses). Promotion into
  `criteria/` plus the three one-line kernel_check pins is the staged
  transition: closure stops being an audit finding and becomes a property
  the gate enforces. A/B/C/D fix instances; F prevents the species.

## Why this is the convergence mechanism

The root names every implementation that passes the criteria. Today that
class contains members that cannot run the repository's own gate, cannot
be layered by its own selfclaim, and cannot be driven by callers written
against the shipped tool. Each pin above removes a family of
useless-but-conforming members — the hashes start converging toward
implementations that are not merely gate-passing but *substitutable for
the shipped tool under the repository's own machinery*, which is
consumer-relative sufficiency applied to reticuli itself, with the gate
as its own first consumer.
