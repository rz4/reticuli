# Fold the verdict cache into `audit`

*2026-10-02, proposal — held for the keyholder. The prototype
(`research/harness/scaling/`, record
`research/provenance/experiment-2026-10-02-verdict-cache.md`) showed the
mechanism root-neutrally; this is what it would take to make it real.*

## The claim

`audit` should consult the provenance ledger as a content-addressed,
trust-weighted verdict cache, re-earning only cache misses, and should
state in its verdict which layers it trusted and which it re-earned cold.
This turns the O(whole claim) audit cost into O(the frontier) without
weakening the guarantee — a hit is the honest statement "a trusted earn of
this exact key exists," printed as such.

## Status (2026-10-02): the claim-level cache already existed; the
## per-component cache is now built

Building this surfaced that reticuli already shipped the claim-level half:
`src/reticuli/reuse.py` + `ret audit --reuse` memoize a whole-claim verdict
under exactly the key this proposal derived (root ‖ build digest ‖
platform ‖ interpreter), reported `reused` never `earned`, pinned by
`measure_check`. The prototype rediscovered it at a finer grain.

What was genuinely missing — and is now built (commit on `main`, root
unmoved, generated-module change) — is **per-component reuse in the deep
audit**. `registry.audit_deep` re-earns every component in the chain
(`_layers`); it now accepts an injected `auditor`, and the surface passes
a reuse-aware one from `reuse.reusing_auditor()` when `--reuse` is set.
The exchange layer stays reuse-agnostic (it cannot reach up to the measure
layer that owns the cache); the measure layer injects the behaviour. Net
effect: an unchanged claim short-circuits at the top as before, a
one-layer change now re-earns only that layer, and a composed audit costs
the frontier instead of the whole chain. Trust is `self` only, by design
for now; the policy rides in the verdict so it can be echoed.

Also now built: a **layered self-audit** (`reuse.layered_audit` in `src`,
driven for the repo by `scripts/selfaudit.py`), so the per-component reuse
reaches the repository's own audit even though the repo is not yet a
composed claim. It earns each selfclaim layer against the live `src/`
bytes with reuse — measured 17s cold, 0s unchanged, 2.6s for a
top-layer change, 17s for a base-layer change. Root-neutral; records in
`research/provenance/revision-2026-10-02-layered-self-audit.md`.

What remains staged below: pinning the behaviour in criteria (Part 2, a
transition), the cross-signer trust policies `signed` / `quorum` (the
shared, distributed cache), which `reusing_auditor` and `layered_audit`
refuse today rather than pretend to offer, and the fully principled
repo-as-composed-claim (so the sandboxed `audit_deep` applies directly
rather than `layered_audit`'s staged-check earn) — itself a transition
because it changes how the repository seals.

## In two parts, because they sit on different sides of the root

**Part 1 — the mechanism (a generated-module change, outside the root).**
`src/reticuli/` is the equivalence class; changing how `audit` works does
not move the repository root. So the cache can be built into `audit`
first, and measured, with no transition:

- key a layer/claim by `sha256(check_bytes ‖ judged-implementation-bytes)`,
  the latter including everything the check depends on (the prototype's
  cumulative-module hash; in the kernel, the claim's own
  dependency-resolved inputs);
- store earned verdicts in the ledger with the provenance already recorded
  (machine, signer, time), which the record format carries today;
- on audit, accept a layer on a trust policy and skip its cold earn;
- print the hit/miss breakdown and the policy used.

This part is testable immediately: a warm self-audit should drop from ~26
minutes to the cost of whatever actually changed.

**Part 2 — making it enforceable (criteria, a transition).** For the cache
to be part of what reticuli *promises* rather than an implementation
convenience, the criteria must pin it, and that moves the root:

- `verification.md` (normative) states what a cached verdict means and
  that a hit requires a trusted earn under a declared policy;
- a criterion pins the key construction (same check + same judged bytes →
  same key; any change → a new key → a miss) and the honest-verdict
  contract (the audit must report hits vs cold earns, never present a hit
  as a cold re-earn);
- the cost envelope is re-read as a *per-miss* bound (reject a layer whose
  cold earn overruns its declared envelope), which is the tractable form
  of pinning performance the succession rerun argued for.

## The trust-policy decision (the keyholder's)

What counts as a hit is the whole design, and it is a values call, not an
engineering one:

- `self` — only your own past earns. Safest, least sharing; a fresh
  machine still pays full cost once.
- `signed:<release>` — trust the signed release's earns. A newcomer
  auditing a release pays only for what they changed from it.
- `quorum:k` — any root with k independent crosschecking earners in the
  ledger. This is the distributed shared cache the open call becomes; the
  prototype showed k=2 trusting the kernel from one simulated stranger.

Recommendation: implement all three, default to `self`, and make the
policy an explicit flag that the verdict echoes — so a cheaper audit is
always a louder statement about whose trust it rests on, never a silent
one.

## What it does not change

The cold earn is unchanged — a miss is still re-earned exactly as today,
sandboxed and from nothing. The cache only decides *what* to skip, never
*how* to earn. And a hit never hides: the whole point is that the audit
says "I trusted these, I re-earned those," which is strictly more
information than today's all-or-nothing verdict, not less.
