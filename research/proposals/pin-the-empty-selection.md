# Proposal — a pattern may select the empty set

*Staged 2026-10-10, from r20 (codex) — the first NEW trial-found seam
since r16, and the first seam the instrument sweeps did not find first
(the completeness sweep never conceived of glob emptiness; pre-registered
prediction P5 falsified exactly as written). A criteria edit in the
authoring layer; a root move; staged for the keyholder. Measured both
ways before staging.*

## The finding

r20 grew 21/21 at e2f40063, passed the held-out battery and the full
bootstrap INSIDE the trial claim's gate, then failed identity in 21
seconds: the substituted repository gate crashed while self_check rebuilt
the chain, because `scripts/selfclaim.py` packs every layer with the
same three glob patterns (`reticuli/*.py`, `reticuli/_kernel/*.py`,
`reticuli/_cli/*.py`) and the EARLY layers contain no `_cli/` files —
the pattern legitimately selects nothing. The original treats a no-match
pattern as an empty selection (glob, sorted, yields nothing); r20's
regrown pack RAISES `pattern names no file`.

The r10 pin made patterns EXPAND in both `generated` and `inputs`; no
fixture ever declared a pattern matching ZERO files, so emptiness-as-
valid is the unexercised half of the glob contract — the same family as
r10, the opposite edge. Measured: a pack with one matching and one
empty pattern PACKS under the shipped tool and is REFUSED by r20's.
(Raising on emptiness is defensible typo-protection in isolation, but it
diverges from the class on a path the chain exercises twenty layers
deep; the set semantics of format 4 also argue for it — an empty set is
a set.)

## What to pin

An authoring_check fixture: pack with a declared pattern that matches no
file alongside one that does; the claim seals, the empty pattern
contributes no steps, and the sealed claim verifies and audits. Bites
r20, passes shipped — measured before staging.

## Status

STAGED for the keyholder. A root move; landing resets nothing banked
(the final set has no counting trial yet) but regrows trial 1 again at
the new root.
