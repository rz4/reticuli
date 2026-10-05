# Proposal — pack authors at format 3 by default

*Staged 2026-10-05, from the first cross-judging run
(`research/harness/crossjudge/`). A contract decision for the
keyholder; nothing here moves a root until signed.*

## The finding

Three kernels packed the same content — same criteria, same recipe
request — and minted two names. The original's `pack` writes a default
`request = "regenerate <output> to pass the gate"` line into every
produce step; both regrown descendants omit it, independently agreeing
with each other against their parent. No criterion pins that text, and
none should: it is producer guidance, and the project's own doctrine
(format 3, spec/claim-format.md) says guidance cannot reject a
realization and therefore is not identity. But `pack` defaults to
format 1, where the raw recipe — guidance included — is hashed. So the
default-authored claim's identity contains words no criterion judges,
and any conforming reimplementation of `pack` mints a different name
for the same claim.

## The decision this asks for

New claims authored by `pack` default to `claim_format = 3`. Then the
default guidance line (keep it or drop it — it is genuinely useful to a
producer) stops being identity, and three correct kernels mint one
name, which is what interchange requires. Existing sealed claims are
untouched: format is per-claim and recorded in the recipe; no existing
root moves. The repository's own claim is already format 3.

## What must be pinned if accepted

`authoring_check` gains two exercised facts: (1) a default `pack`
writes `claim.format = 3`; (2) two packs of identical content that
differ only in guidance mint the same root. That is a criteria edit —
a root move — hence the signature gate.

## The alternative, named honestly

Declare authoring-era freedom instead: same content may mint different
roots across implementations, and interchange is only promised for
claims that travel (export/import), never for parallel authorship.
That reading makes "the root names the claim" weaker than the README
says it is. The proposal recommends format 3 by default.
