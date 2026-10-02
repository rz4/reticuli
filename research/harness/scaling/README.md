# Scaling: the audit as a content-addressed verdict cache

*Research tooling — not normative, not pinned. Nothing here moves a root.*

## The wall

An audit re-earns every verdict cold, from nothing. That is reticuli's
whole guarantee, and it is inherently O(the entire claim): a one-line
change costs the same full re-derivation as a rewrite. The succession
rerun measured the bill — a regrown tool's self-audit runs ~26 minutes,
dominated by rebuilding all nineteen layers, and overruns the repository's
own declared audit ceiling. As the claim grows, the guarantee gets more
expensive, forever.

## The idea (the keyholder's)

Most of the time, a machine has already earned most of the layers. What
you actually need to regenerate is the **cache miss** — the layer whose
criteria or implementation changed since a trusted earn. So treat the
audit as a cache:

- **The key is content-addressed.** A layer's key is two hashes: the
  bytes of its acceptance check (what it pins) and the bytes of the
  implementation it judges — its own modules *and every module beneath
  it*, so a change low in the stack invalidates everything above and
  nothing below. A changed check or module is a *new key*, hence an
  automatic miss; content-addressing makes cache invalidation free. (This
  is the same move Nix and Bazel make; reticuli's root was a derivation
  hash all along.)
- **The value is an earned verdict with provenance** — who earned it, on
  what machine, when, how long it took. The provenance ledger already
  holds exactly this; the audit simply never consulted it as a cache.
- **Trust is a policy, stated in the verdict.** A hit means *someone you
  accept* earned this key. `self` trusts your own past earns; `signed:X`
  trusts a named signer; `quorum:k` trusts any key with k independent
  earners — the shared, distributed cache the open call becomes. The
  audit prints which layers it trusted and which it re-earned cold: a
  weaker claim stated honestly, never a strong one faked (the
  `unknown`-not-faked principle, applied to the tool's own cost).

Steady-state audit cost becomes O(the frontier) — only what changed. A
cold machine pays once; every audit after pays the diff; and across a
network, every crosschecked earn shrinks the frontier for the next
person.

## Run it

    python3 cache_audit.py --reset --policy self   # cold: all miss, pays full
    python3 cache_audit.py --policy self           # warm: all hit, ~0s
    python3 cache_audit.py --dry                    # classify, do not earn

`RETICULI_CACHE_MACHINE` / `RETICULI_CACHE_SIGNER` label an earner, so a
shared cache with several earners can be simulated for `--policy quorum:k`.
The store is `cache_store.json` (runtime state, gitignored); the layer
structure and per-layer checks come from `scripts/selfclaim.py`.

## What it shows

See `research/provenance/` for the recorded run: the cold cost, the warm
re-audit dropping to seconds, dependency-aware invalidation (touch the
core layer and everything above misses; touch the top and only it does),
and the quorum policy turning independent earns into hits.

## The honest limit, and where it went

This is a prototype beside the kernel, not inside it. It earns each layer
by running its check in a staged room (the way `selfclaim` seals it),
which is an honest cold earn but not the kernel's sandboxed `audit`.

Folding it in revealed the tool already had the claim-level half —
`src/reticuli/reuse.py` + `ret audit --reuse`, same key, same
`reused`-not-`earned` discipline, pinned by `measure_check`. The missing
half — per-component reuse so a composed claim skips unchanged layers — is
now built into the shipped deep audit (root-neutral; see
`research/provenance/revision-2026-10-02-per-component-reuse.md`). This
harness remains the readable, measurable model of the idea; the proposal
in `research/proposals/` tracks what is shipped versus staged.
