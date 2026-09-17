# Format 3: guidance leaves the root (a capability, not yet adopted)

This documents a capability the kernel now has and **nothing has adopted**.
No claim in this repository declares `format = 3` yet; every root is
unchanged. Adopting format 3 — migrating the repository, the kernel claim,
and the examples to it — moves every root, and that migration is the
keyholder's acceptance act, not the tool's. This file is the design and the
proposal; the adoption is a separate, deliberate step.

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

## What adoption would entail (the acceptance act, held for the keyholder)

1. `spec/identity.md` and `spec/claim-format.md` state the format-3 preimage
   and the criterion/guidance distinction, and mark which spec sentences a
   verifier enforces.
2. New format-3 conformance vectors land beside the format-1/2 ones in
   `spec/vectors/`; the old ones stay.
3. The repository, the kernel claim, and the examples migrate to
   `format = 3`, renaming `request` to `guidance`. Every root moves; each
   old↔new pair is attested, per the compatibility promise.
4. The kernel suite pins the format-3 behavior — a kernel revision (v2.4),
   which orphans the v2.x proof and needs a fresh rebuild to re-earn it.
5. The repository root/promise split (README, packaging, logo, workflow to a
   separate context digest) rides the same acceptance act, so the repository
   root becomes purely the address of its acceptance boundary.

Each of these changes what a root means. None is done here.
