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
- **F. The closure check (the general repair).** A new criterion that
  walks every pinned file's imports and attribute uses into the generated
  package and asserts each consumed name appears in some check's pinned
  surface. That turns "the gate is closed over its class" from an audit
  finding into a property the gate itself enforces, permanently. A/B/C/D
  fix today's instances; F prevents the species.

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
