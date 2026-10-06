# Proposal — the recipe is present when the warm gate runs

*Staged 2026-10-06 (night of trial 1), from the r5 substituted-gate
refusal. A contract decision for the keyholder; nothing here moves a
root until signed.*

## The finding

The r5 tree's `pack` performs the warm ritual in this order: run the
gate, hash the verdict, THEN write the recipe into the room. The
original writes the recipe first. Nothing pins the order — and the
repository's own layer checks stand on it: every chained criterion
writes its verdict only when a recipe file is present (the
am-I-in-a-claim guard, `reticuli.toml` or `claim.toml`). So the r5
pack, building the self-claim chain, ran each layer's check in a room
with no recipe: the battery passed, the guard said "not a claim", no
verdict was written, and the seal crashed hashing a verdict that never
existed. `self_check` refused the tree at the whole-repo level —
layer-admissible, repo-inadmissible, the third finding of that class
in two generations.

`authoring_check` cannot see this: its fixtures' checks write their
verdicts unconditionally. The pinned repository checks are the only
gates whose verdict-writing is conditional on the room's shape, and
they only meet a foreign pack inside `self_check`.

## Why the contract should say "recipe first"

The gate judges a CLAIM, and a claim includes its recipe — the
room-matches-the-name doctrine (revision-2026-09-28). A gate that runs
before the recipe exists is judging a pile of files, not a claim; a
criterion is entitled to ask "what claim am I in?" (several do), and
format-3 rooms must receive the preimage recipe for exactly this kind
of reading. The order is not implementation taste; it is what makes
the warm verdict mean "earned inside the claim it certifies".

## What must be pinned if accepted

`authoring_check` exercises it: a fixture whose CHECK writes its
verdict only if the recipe file is present (the repository's own guard
pattern) seals through `pack` — so any pack that gates before writing
the recipe fails to seal the fixture. One assertion, one fixture
edit — a root move — hence the signature gate.

## Effect on the closure count

Unsigned, the count's arithmetic is untouched (r5 was already refused
by the identity gate, so trial 1 does not qualify regardless). Signed,
the boundary learns and the next generation faces the pin — the
ordinary ratchet, still turning, which is itself the honest status: we
are demonstrably not at the fixpoint yet.

## Status

Signed by the keyholder 2026-10-06 ("I sign off. work till the r6
run") and landed the same morning as one bundle with its two siblings
(one root move; see the provenance record
revision-2026-10-06-recipe-first-bundle.md).
