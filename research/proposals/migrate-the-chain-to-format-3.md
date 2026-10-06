# Proposal — the self-claim chain migrates to format 3

*Staged 2026-10-06, from closure trial 1 second attempt (r6). A
contract decision for the keyholder; nothing here moves a root until
signed — and this one moves every chained layer root at once, by
design, exactly once.*

## The finding

Under the r6 tree, the substituted gate's chain build completes and
every layer's gate passes — and the lockfile refuses, because the
layer roots drift chain-wide. The drifting byte: on component-supplied
steps the original pack writes `request = "supplied by the <component>
component"`; the r6 pack writes none. Both are conforming — no
criterion pins the supplied-step guidance text, and by doctrine none
should — but the chain's layers are deliberately format 1, where
guidance IS identity. So any conforming foreign pack mints different
layer roots for the same chain, and `self_check` can only pass under a
pack whose incidental wording matches the original's. This is the
cross-judging authoring divergence (author-at-format-3, signed
2026-10-05) resurfacing in the one place the format-3 default cannot
reach: the chain pins `claim_format=1` on purpose, to keep its
era-1 roots stable.

## The decision this asks for

Migrate the nineteen chained layers (and the reference layer) to
format 3 — the "deliberate migration" the selfclaim comment has
anticipated since the format was introduced. Guidance leaves every
layer root; the chain becomes mintable by ANY conforming pack; the
self-claim lockfile stops encoding the original pack's incidental
wording. One re-pin of the whole PINNED dict, one reseal, one
signature — and the r6-class drift becomes impossible by construction
rather than pinned away word by word.

## The alternative, named honestly

Pin the supplied-step request text in authoring_check (words that
judge nothing, pinned purely to stabilize format-1 hashes), or accept
that self_check admits only wording-twins of the original pack. The
first is doctrine-violating; the second makes the identity gate
quietly test prose instead of criteria. The migration is the move the
format was built for.

## Cost and blast radius

Every chained layer root moves once; the lockfile re-pin is mechanical
(`python3 scripts/selfclaim.py`), the repository root moves once, and
the roots are thereafter implementation-wording-independent — the same
robustness the reference layer gained when its modules became
generated steps. No shipped claim outside the chain is affected.

## Status

Signed by the keyholder 2026-10-06 ("I sign them continue to r7") and
landed the same day as one bundle with its two siblings (see the
provenance record revision-2026-10-06-the-migration-bundle.md).
