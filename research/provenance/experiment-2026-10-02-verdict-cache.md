# The audit as a content-addressed verdict cache

*2026-10-02. Research record — a prototype, not normative, no root moved
(repository root `cfb038bf…` throughout). Tooling:
`research/harness/scaling/cache_audit.py`.*

## Why

The succession rerun measured reticuli's scaling wall: a regrown tool's
self-audit runs ~26 minutes and overruns the repository's declared audit
ceiling, because an audit re-earns every verdict cold — inherently O(the
whole claim), every time. The keyholder's reframing: a machine usually has
most layers already earned; what you must regenerate is the *cache miss*.
This prototype builds that cache over the nineteen self-claim layers and
measures what it buys.

## The design

Each layer gets a content-addressed key: `sha256(check_hash ‖ impl_hash)`,
where `check_hash` is the bytes of the layer's acceptance check and
`impl_hash` is the bytes of every module it judges — its own and all
beneath it. A cache entry is an earned verdict with provenance (machine,
signer, time, seconds). Trust is a policy over entries: `self` (your own
earns), `signed:X` (a named signer), `quorum:k` (k independent earners).
A `caching_audit` skips layers the policy accepts and earns only the rest,
printing which were trusted and which were re-earned.

## What it showed (one M1 machine)

**The scaling win — cold to warm.**

    cold (empty cache):  19/19 earned,  16.6 s
    warm (self policy):  19/19 trusted,  0.0 s

The second audit pays nothing for what did not change. (The absolute cold
figure is the per-layer check cost; it is lighter than the real sandboxed
`ret audit` — ~26 min — because the prototype runs each check against
staged bytes without the pack/seal/sandbox overhead. The savings *ratio*,
not the absolute, is the transferable result: whatever a layer's cold cost,
the cache spends it only on misses.)

**Dependency-aware invalidation — O(the frontier), correct direction.**
Against scratch copies of src and criteria (the repo untouched):

    unchanged (different directory):   19/19 hit   — keys are content, not path
    touch _kernel/core.py (the base):   0/19 hit   — all depend on core
    touch cli.py (the top):            18/19 hit   — only `surface` misses
    reword surface_check.py:           18/19 hit   — a changed check is a new key

A change at the foundation invalidates everything above it; a change at
the top invalidates only the top; a reworded criterion invalidates exactly
its own layer. Content-addressing makes this free — there is no
invalidation logic, only keys that do or do not match.

**The network as a shared cache — quorum trust.** Seeding the ledger with
one simulated stranger's earn of the eight kernel layers, then auditing
under `quorum:2`:

    8/19 trusted (2 independent earners: me + stranger)
    11/19 frontier left to earn

The more independent earners a root has in the ledger, the smaller the
frontier each newcomer pays for. The open call stops being charity and
becomes a distributed cache that gets cheaper to trust as coverage grows.

## The reading

Reticuli's root was a content-addressed derivation key all along; the
provenance ledger was a cache of earned verdicts all along. The audit
simply never consulted them as such. Consulting them turns the O(whole
claim) wall into an O(frontier) cost, without weakening the guarantee into
a lie: a cache hit is the honest statement "someone I accept earned this
exact key," and the audit says so, per layer. That is the
`unknown`-not-faked principle turned on the tool's own cost — a weaker
claim, stated plainly, instead of a strong one, faked.

Two things fall out that the earlier framing missed:

1. The purity-versus-cost fork dissolves. The cost envelope (reject a
   too-slow implementation) is the *miss* cost — local, per-layer,
   machine-comparable — not a whole-audit wall clock. Incremental audit
   and cost-pinning are the same path from two ends.
2. Invalidation direction is a real, visible property of the layer DAG:
   foundations are expensive to touch (wide blast), surfaces are cheap.
   That is a design pressure the decomposition already answers and the
   cache now makes legible.

## The honest limit, and the real next step

This earns each layer by running its check in a staged room, not through
the kernel's sandboxed `audit`; it is a prototype beside the kernel, not
inside it. The real step is folding the cache into `audit` itself — see
`research/proposals/verdict-cache-in-audit.md`. That is a design change to
a generated module (outside the root) plus, to make it enforceable, new
criteria (a transition). Staged for the keyholder, not taken.
