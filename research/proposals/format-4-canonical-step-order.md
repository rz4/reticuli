# Proposal — format 4: the step list is a set

*Staged 2026-10-06, from closure trial 1 third attempt (r7). A
contract decision for the keyholder; nothing here moves a root until
signed — and like the migration before it, this one moves every
migrated root exactly once, by design.*

## The finding

The format-3 migration did its job: no guidance byte can drift a layer
root. The r7 trial immediately exposed the next member of the same
family: the recipe's step ORDER. The r7 pack emits produce steps in
full lexicographic order; the original emits them in glob-pattern
order (top-level modules before `_kernel/*`). Same step set, same
criteria, different array order — and the order sits inside the
serialized recipe, so it is identity. The split first bites exactly
where the two orders first disagree — `kernel.py` sorting after
`_kernel/*` at the crosscheck layer — and cascades upward through
component links: 13 of 20 layer roots moved under the r7 pack
(subst7 measurement; the kernel sub-chain's orders happen to agree, so
it held). The r6 drift was wording; the r7 drift is sequence. The
family is "authoring FORM is identity," and its members fall one per
generation.

## The decision this asks for

Format 4: the identity preimage canonicalizes the step list —
serialize steps sorted by their `output` (the one key every step has
and no two steps share) — so array order leaves the root exactly as
guidance left it at format 3. Order cannot reject a realization;
canonical form is the doctrine already applied once. The chain (and
the repository claim) migrate; every migrated root moves once; any
conforming pack thereafter mints the chain's roots regardless of its
emission order OR its wording — closing the authoring-form family by
construction rather than member-by-member.

## The alternative, named honestly

Pin pack's emission order as a convention in authoring_check (the
original's glob-pattern order, or sorted — either way pinning
presentation, not judgment, and leaving the next form-member — key
order? whitespace in embedded strings? — to the next generation). The
format-4 route closes the class; the convention route closes the
instance. After watching wording and order fall in consecutive trials,
the proposal recommends closing the class.

## Cost

An identity-layer change (`_preimage_recipe` grows the sort at
format 4) plus the migration: identity_check pins the new format's
behavior, the chain declares format 4, the lockfile re-pins once, the
repository reseals once. The reference implementation must mirror the
transform or vectors split — which is exactly what the vectors exist
to catch.

## Status

Signed by the keyholder 2026-10-06 ("I sign off on them, start working
on r8") and landed the same day as one bundle with its sibling (see the
provenance record revision-2026-10-06-format-4-and-the-hour.md).
