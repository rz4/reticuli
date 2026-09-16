# Lineage: which v1 claim each v2 claim descends from

**Status: prepared, UNSIGNED.** This file states the correspondences and the
evidence for them. Binding them is a signing ceremony — the keyholder's act,
never an agent's. Nothing here is a signature, and nothing here should be
read as one.

## Why a correspondence is needed at all

v2 roots do not equal v1 roots, and cannot: the recipe text is inside the
hash preimage, and v2 renamed the recipe's keys (`[record]` → `[claim]`,
`class = "free"` → `"generated"`) alongside the preimage's own spelling
(`seed:`/`pin:` → `input:`/`pinned:`, plus an in-band `digest` field). Two
claims that demand the same behavior therefore carry different names. The
break was deliberate (`spec/identity.md`), so the link is asserted by
attestation rather than discovered by hash equality.

## The pairs

### quirkcalc — the teaching example

| | root | evidence |
|---|---|---|
| v1 | `dc3c695f10cacbeb34fe480dde59b7c77f3652628e0be727ea86082ae459e2dc` | reticuli-lab `docs/experiments/quirkcalc` |
| v2 | `03d039ca6878609359e5770866377edf40a26eff48bdb1147e300aecee26f175` | `examples/quirkcalc` |

The strongest pair: the pinned inputs are **byte-identical** across the two
(the same `check_calc.py` and the same 59 `cases/*.txt`, copied unchanged).
Only the recipe differs, and only in the v2 renames. So the two roots name
the same acceptance criteria over the same data, and a verifier can confirm
that claim by hashing the input files on both sides — no trust required.

### kernel — the seed claim

| | root | evidence |
|---|---|---|
| v1 (`kernel-core`) | `fb3cdc74d9a0da9aed7ad5f04ecba59d4822c6073b879861eebd20d8a4e390fe` | reticuli-lab `.reticuli/liquid/kernel-core` |
| v2.0 (`kernel`) | `d64cc301082f420f4541150618d8774c0ea6c1fc7015b15ce7fd001343ccb405` | `conformance/kernel-2.0/` — proven, superseded |
| v2.1 (`kernel`) | `4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382` | `conformance/kernel/` — current, proof pending |

The kernel's lineage is three links, not two, and the last one is a
*succession within v2*: the v2.1 suite is the v2.0 suite plus seven pinned
behaviors (`revision-2026-09-15.md`). Unlike the v1↔v2 pair, this succession
is checkable by direct comparison — both suites are in this repository, and
the diff is additive: no existing assertion was weakened, deleted, or
reordered. A verifier can confirm that claim rather than take it.

A weaker pair, and the difference matters. The acceptance suites are not
byte-identical: v1's is 1,117 lines (`sha256 6d889318e118f28e…`), v2's is
1,132 (`sha256 bd9bc90d2ccce5c5…`), because the vocabulary translation
rewrote identifiers, embedded recipes, prose — and **recomputed the six
golden root vectors**, which had to change, since they pin the v2 preimage.

What supports the correspondence is not byte equality but a recorded
translation: the v2 suite's AST node sequence is identical to v1's (7,627
nodes — renames only, no logic, ordering, or count changed), audited at the
time and recorded in `bootstrap.md`. A verifier who wants to check this must
re-derive that AST comparison; it is evidence, not proof.

## What a signature over these pairs would and would not mean

It would assert: *the same keyholder vouches that these two roots name the
same claim under two formats, on the evidence above.* It would not assert
that the roots are derivable from one another (they are not), nor that v1
artifacts verify under v2 tooling (they do not — the formats differ).

## Not yet paired

`reticuli` (v1 whole-repo, `81bfc78b…`) has no v2 counterpart: v2 drops
nine-rung self-hosting as its architecture, so the whole-repo claim will be
re-expressed as a single worked example rather than ported one-to-one. The
v1 execution/jester and other rung roots likewise await their v2 layers.
