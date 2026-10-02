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
