# Proposal — the sandbox signal must survive the public surface

*Staged 2026-10-06 (night of trial 1), from the r5 cross-judging
anomaly. A contract decision for the keyholder; nothing here moves a
root until signed.*

## The finding

The r5 tree passes `build_check` — its build layer's rebuild result
names its jail, as pinned yesterday. But the tree's PUBLIC
`kernel.rebuild` (the crosscheck layer's wrapper, which is what every
caller actually touches) reimplements rebuild rather than delegating,
and its result drops the top-level `quarantine` key (it keeps the
per-gate rows). Nothing pins the wrapper's result shape, so the pin
held at the layer it was written against and evaporated one layer up,
at the surface users see. The cross-judging matrix — which drives the
public API, like any user — read `None` where the original says
`seatbelt`.

Reimplementation instead of delegation is legitimate (internal seams
are declared free; the original's kernel.py happens to delegate, but
that is implementation, not contract). What the contract must say is
that the PUBLIC result carries the signal, however the inside is
arranged.

## What must be pinned if accepted

`kernel_check` (the crosscheck layer owns kernel.py) exercises:
`kernel.rebuild`'s result carries `quarantine` from the closed
vocabulary at the top level, and `kernel.audit`'s gate rows carry it —
the same two facts build_check pins one layer down, asserted against
the surface a caller reaches. A criteria edit — a root move — hence
the signature gate.

## The general lesson, worth recording

A pin binds the layer whose check exercises it, and a chained
architecture lets an upper layer lawfully rebuild the same verb from
scratch. Any pin on a result SHAPE must therefore be asserted at every
layer that re-exposes the verb — or, cheaper, at the outermost one,
since the inner layers' checks already hold their own. The closure
criterion catches consumed NAMES that vanish; it cannot catch a key
that a wrapper's fresh dict never mentions. This is the first seam of
that species; the register should name the species, not just the
instance.

## Effect on the closure count

By the k=3 rule, only an ADOPTED counterexample resets the count.
Whether this is adopted is exactly the keyholder's call: unsigned, r5
can still qualify on the pinned bar it faced; signed, the boundary
learns and the count honestly returns to zero. The bar was designed to
force precisely this choice into the open.

## Status

Signed by the keyholder 2026-10-06 ("I sign off. work till the r6
run") and landed the same morning as one bundle with its two siblings
(one root move; see the provenance record
revision-2026-10-06-recipe-first-bundle.md).
