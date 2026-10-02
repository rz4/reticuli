# Per-component reuse in the deep audit

*2026-10-02. A generated-module change — `src/` is the equivalence class,
so the repository root does not move (`cfb038bf…` throughout). Not a
transition; recorded here because it changes what `audit` does, and the
record of why belongs with the code.*

## What changed

`ret audit --reuse` already memoized a whole-claim verdict (the shipped
`reuse.py`, keyed by root ‖ build digest ‖ platform ‖ interpreter,
reported `reused` never `earned`). That is all-or-nothing: an unchanged
claim is instant, but any change re-earns the whole thing. The deep audit
(`registry.audit_deep` → `_layers`) re-earned every component in the chain
cold, every time — the real O(whole-claim) cost for a composed claim.

Now the deep walk reuses per component. Three additive, root-neutral
edits:

- `registry.audit_deep` / `_layers` take an optional `auditor`
  (default `kernel.audit`), called to re-earn each component. The exchange
  layer stays reuse-agnostic — it cannot import the measure layer that
  owns the cache, so the behaviour is injected from above, not reached
  down for.
- `reuse.reusing_auditor()` (measure layer) is that injected auditor: it
  keys a component by the SUBSTITUTED bytes the dependent ships for it
  (`component_fingerprint`, a supplied-bytes digest, not the component's
  own sealed build digest), skips a hit as `reused`, and re-earns a miss
  cold through `kernel.audit`, recording it. `reuse.py`'s existing
  `lookup`/`remember`/`fingerprint` are unchanged (their pinned round-trip
  holds); the new paths factor through shared `_lookup_fp`/`_remember_fp`.
- the surface passes the reuse-aware auditor into `audit_deep` when
  `--reuse` is set.

## Why it is safe without a root move

`src/reticuli/` is generated, outside the root; the change is additive and
default-off (no `auditor` → `kernel.audit` → today's behaviour exactly), so
every criterion that calls `audit` or `audit_deep` positionally is
unaffected. Confirmed: `measure_check` (pins the reuse round-trip) and
`exchange_check` (pins `audit_deep`) pass against the living tree, the
repository root recomputes unmoved, and the full gate re-earns `REPO_OK`.
A functional test on a two-layer composed claim shows the component
`earned` on the first audit and `reused` on the next.

## What it buys, and what it does not

Buys: a composed audit now pays for the frontier, not the whole chain —
an unchanged claim short-circuits at the top, a one-layer change re-earns
only that layer. This is the scaling answer the succession timing finding
asked for, built on the primitive the codebase already had.

Does not: trust beyond `self`. A hit still rests only on this machine's
own past earn; `reusing_auditor` refuses `signed`/`quorum` rather than
pretend to offer the shared cache. And the behaviour is not yet pinned in
criteria — reuse remains opt-in convenience, not a promise. Both are
staged in `research/proposals/verdict-cache-in-audit.md`; the second is a
transition for the keyholder.
