# Proposal — pack authors at format 4 by default

*Staged 2026-10-06, alongside the format-4 bundle but deliberately NOT
included in it: the signed proposal migrated the chain and the
repository claim, and said nothing about fresh authoring. This is the
leftover question, written down rather than assumed.*

## The finding, by analogy

Format 3 became the authoring default (signed 2026-10-05) because
three conforming kernels minted two names for one authored claim: the
divergent byte was pack's default guidance wording. Format 4 exists
because the same thing happened one level down, on step ORDER, and
drifted 13 of 20 chain roots (r7). The chain and this repository are
migrated. Fresh claims authored by `pack` are still born at format 3,
so two conforming packs that emit the same steps in different orders
still mint different names for the same new claim.

It has not bitten yet in the cross-judging matrix — the toy claim has
two steps and every sampled pack happens to order them alike — so this
is a latent instance of a class we have twice watched become live.

## The decision this asks for

`pack` defaults new claims to `claim_format = 4`. Then neither wording
nor order is identity for anything authored from here, and the
"three kernels, one name" property the matrix measures holds against
step-order divergence as well. No existing root moves; format is
per-claim.

## What must be pinned if accepted

`authoring_check`'s format-default assertion moves from 3 to 4, and
its guidance-neutrality fixture gains an order-neutrality twin (two
packs of the same content, steps emitted in different orders, one
root). `tests/test_manifest.py` follows the default as it did last
time. A criteria edit — a root move — hence the signature gate.

## The alternative, named honestly

Leave the default at 3 and let each author opt in. Defensible only if
there is a reason to want order in a new claim's identity, and nobody
has named one; the cost of waiting is that the next conforming
authoring tool we meet may mint a different name for a claim written
today.
