# Proposal — pin the deep audit's transitive closure

*Staged 2026-10-05, from the r4 succession run's identity judgment. A
contract decision for the keyholder; nothing here moves a root until
signed.*

## The finding

The r4 regrown tree passed all twenty per-layer gates and then FAILED
the repository's substituted full gate — refused by `self_check`'s deep
audit assertion. The cause: the regrown `registry.audit_deep` recurses
exactly one level (the claim's direct components), where the original
walks the whole transitive chain. Surface's deep audit judged 1 layer
instead of 18.

The seam is real and sampled twice: the r3 codex tree's `audit_deep`
is also one-level (r3 never ran the full gate, so it went unjudged),
while the r2 tree's recursed fully and passed. Independent draws fill
the depth differently because nothing pins it: `exchange_check`
exercises `audit_deep` on a fixture chain too shallow to force
recursion, so one level of traversal satisfies everything the layer
gate asks. A layer-admissible module that is repo-inadmissible — the
gate-closure class of finding, one level up.

## Why this is worth a pin

Composed audit is the verb a recipient runs on a chain they received:
"every component re-earns its verdict on the bytes this claim ships."
If the traversal depth is implementation-defined, a conforming kernel
can report a deep chain healthy after checking its first link — the
exact lie composed audit exists to prevent. Today the whole-repo
boundary catches it only incidentally (self_check counts layers), and
only on the repository's own chain.

## What must be pinned if accepted

`exchange_check` exercises `audit_deep` on a chain at least THREE
claims deep and asserts every ancestor beneath the top appears in
`layers`, each re-earned (and a broken grandparent fails the composed
verdict — depth must propagate refusals, not just visits). A criteria
edit — a root move — hence the signature gate.

## The alternative, named honestly

Declare depth implementation-defined and make recipients loop over the
chain themselves. That reading makes `audit_deep` a convenience nobody
can trust, and the name a small lie. The proposal recommends the pin.

## Status

Signed by the keyholder 2026-10-05 and landed the same day as one
bundle with its two siblings (one root move; see the provenance record
revision-2026-10-05-sandbox-closure-bundle.md).
