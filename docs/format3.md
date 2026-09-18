# Format 3: guidance leaves the root

**Adoption status (2026-09-17): the repository's own claim declares
`format = 3`** — its produce steps carry `guidance`, the promise files left
the root in the same act, and the format-3 conformance vectors
(`spec/vectors/v10-…`, `v11-…`) pin the preimage for any implementation.
The kernel claim (`82a81357…`) and the examples remain at formats 1 and 2,
deliberately: migrating them moves their roots and orphans the kernel's
proof lineage, so that step is batched with the v2.4 kernel revision and
rides the keyholder's explicit go. The checklist at the bottom of this file
tracks what is adopted and what still waits.

This file was written before the adoption as the design and the proposal;
the sections below are kept as the rationale of record.

## The principle

> A byte belongs to the identity of a claim if and only if changing that
> byte can change whether some realization is accepted.

A step's `request` (renamed `guidance`) is a hint that helps a producer
*find* a realization. It is never consulted when deciding whether a
realization *passes* — the gate does that. So two claims that differ only in
how they word a producer instruction are the same acceptance boundary, and
under the principle they must have the same root. Before format 3 they did
not: the whole recipe, guidance included, was hashed.

## What format 3 changes

At `format = 3`, the recipe is stripped of step guidance before it enters
the root preimage. Concretely: every step's `request` and `guidance` keys
are removed from the copy that is serialized into `parts["recipe"]`.
Everything else is unchanged — `kind`, `output`, `class`, `run`, `from`, and
every `[claim]` field stay, because each can affect whether a realization is
accepted. Formats 1 and 2 serialize the whole recipe exactly as before, so
their roots never move; this is the compatibility promise
(`docs/compatibility.md`) working — a new format, past formats readable
forever.

Both identity implementations (`reticuli.kernel`, `reticuli.reference`)
apply the identical transform, so they agree on every format-3 root.

## Criterion versus guidance

This draws a line the format now enforces:

- A **criterion** is authoritative. It can reject a realization: the gate
  command, the pinned inputs and fixtures, the environment, the declared
  envelope, the pinned verdicts.
- **Guidance** helps a producer discover a realization. It cannot make one
  valid: the `guidance` string on a produce step.

If something currently written as guidance actually expresses required
behavior, it should become a criterion (a check, a fixture, a pinned
specification) — not sit in a string the root ignores. The spec should say,
for each of its sentences, whether a verifier enforces it or it is only
stated human intent; guidance is the part no verifier enforces, and format 3
stops it from silently sitting inside identity.

## The guidance-blind rebuild

Once guidance is out of the root, `ret rebuild --without-guidance` becomes
meaningful: the producer is handed the outputs to write but not the hints
for how, and — because guidance is not in the root — a blind rebuild targets
the same root a guided one does. The two measurements differ in what they
show:

- a **guided** M3 shows the claim can be transported and realized;
- a **guidance-blind** M3 shows the acceptance criteria themselves carry
  enough structure to reconstruct the software.

The gap between them is a measurement of how much of the solution the claim
carries versus how much the hint carried. The producer ledger records
`guidance: true|false` so the two are never confused.

## The adoption checklist (each item the keyholder's acceptance act)

1. **DONE (2026-09-17).** `spec/identity.md` and `spec/claim-format.md`
   state the format-3 preimage and the criterion/guidance distinction.
2. **DONE (2026-09-17).** Format-3 conformance vectors
   (`v10-format3-guidance`, `v11-format3-request`) sit beside the
   format-1/2 ones; both spellings land one root.
3. **DONE for the repository claim (2026-09-17)**: `reticuli.toml` declares
   `format = 3` and its produce steps carry `guidance`; the repository root
   moved and the old→new pair is in the provenance history. **HELD for the
   kernel claim and the examples** — migrating them moves their roots, so
   they ride item 4.
4. **HELD.** The kernel suite pins format-3 behavior — the v2.4 revision,
   which orphans the kernel proof lineage and takes one paid rebuild to
   re-earn.
5. **PARTLY DONE (2026-09-17)**: the promise files (README, packaging,
   logo, workflow) left the repository root. **HELD**: giving the promise
   its own context digest, which wants a kernel feature and rides item 4.

Items still marked HELD change what a root means and wait for the
keyholder's explicit go.
