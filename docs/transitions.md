# Transitions — how a reticuli claim changes

*Informational — the procedure for changing a claim's identity. The pinned
inputs it governs are defined in [`spec/`](https://github.com/rz4/reticuli/tree/main/spec/) and `reticuli.toml`; see
also [`GOVERNANCE.md`](https://github.com/rz4/reticuli/blob/main/GOVERNANCE.md).*

Reticuli's own development is reticuli's protocol applied to itself. A change
that touches the boundary is not an edit, it is a new claim. This page is the
procedure for making one, and it is the same procedure whether a maintainer
runs it today or an outside operator runs it once the call is open.

The change is monotonic. A new root supersedes the old rather than amending
it, roots only move forward, and the room (`room/reticuli`, the blind export)
tracks the latest.

## Two kinds of change

- **Ordinary** changes cover the implementation under `src/`, which is
  generated and excluded from the root, along with `tests/`, `docs/`,
  `research/`, and tooling. These do not move the root. They go through
  normal review and nothing on this page applies.
- **Identity-bearing** changes are anything that edits a pinned input: the
  recipe (`reticuli.toml`), `spec/`, or an acceptance suite under
  `criteria/`. These move the root and follow the procedure below.

To tell which one you are making, look at the recipe's `[claim].inputs` list
and its non-generated produce steps, which are the pinned set. When in doubt,
make the change and run `ret verify .`. If the root moved, the change was
identity-bearing, and a moved root you did not intend is a mistake to undo
rather than to reseal.

## The ritual: add → reseal → reprove → resign

The mnemonic is four verbs and the full checklist is seven steps.

1. **Add.** Make the boundary change, and state why identity must move. A
   moved root is a stronger or more correct claim, never an accident and
   never incidental cleanup.
2. **Reseal.** Recompute the root and write the new manifest:
   `python3 -c "import sys; sys.path.insert(0,'src'); from reticuli import kernel; kernel.seal('.')"`
3. **Re-earn.** Run the gate cold with `python3 gate.py`, so the reference
   passes at the new root, then run `ret audit .` to leave a fresh receipt.
4. **Reprove.** Run an independent blind rebuild from the new boundary. How
   strong this has to be depends on the change; see the accept bars below.
5. **Record.** Write the old-to-new pair in `research/provenance/` as a
   `revision-*.md`, saying what moved and why the root moved with it.
6. **Resign.** A keyholder signs the new root when the change warrants it,
   again according to the bars. No agent signs; the signature is the human
   trust boundary.
7. **Refresh the room.** Re-export the blind boundary so `room/reticuli`
   names the new root, using `ret export . room.tar --blind` and then
   committing the tree onto the room branch.

## The accept bars: how strong the reprove and the signature must be

Not every change deserves a paid rebuild or a signature. The bar scales with
what the change claims.

- **Internal click**, meaning a maintainer correction or hardening. The bar
  is reseal, gate, and a recorded old-to-new pair. Blind reproduction is
  reserved for testing the fixpoint, described below, rather than spent on
  every click. These are not signed, because the signature is the ceremony
  and not a per-commit stamp.
- **External transition**, meaning an operator's submission once the call is
  open. The bar is a blind, any-producer rebuild that lands the root, in
  order to accept the transition. A routine hardening pull request must not
  cost a paid vendor session.
- **Version stamp or completion**, meaning blessing a root as a released
  version. The bar is the full paid ladder against the best independent blind
  reproduction, after which the keyholder signs. This is the ceremony that
  turns a stable root into a version.

## The fixpoint: when the ratchet stops

The boundary is stable when k consecutive independent blind reproductions
land the root with zero adopted counterexamples. That is the stopping rule
for calling a root "very stable" rather than merely "current."

The keyholder set k = 3 on 2026-10-05, with the qualifying conditions spelled
out so that a trial either counts or does not:

1. The root is frozen before the trial, and only the blind boundary is given.
2. The producer is independent and the implementation genuinely distinct.
3. The full conformance gate establishes membership — `gate.py`,
   `ret verify`, `ret crosscheck` — rather than a sampled subset.
4. The recursive step holds: the reconstructed implementation itself performs
   the pinned reconstruction operation, through its own CLI, from a blind
   room, landing that claim's root. A tree that passes every suite but cannot
   reconstruct is a decoy rather than a member, as witnessed by the r4 tree,
   which was refused for exactly this.
5. At least one of the three trials re-earns on a machine and operator
   outside the generation environment, with record, cost, producer
   declaration, and provenance sealed.
6. All three land within the declared `usd` envelope.
7. The three trials span at least two model families, and no boundary change
   intervenes. An adopted counterexample resets the count to zero, which is
   the point: the count only grows while the boundary has stopped learning.

Closure of the reticuli→reticuli arm is exactly this bar being met. Closed
does not mean finished. It means the first-order question is answered, that
the boundary transports enough to re-realize the tool including the
reconstruction operation, and that research effort moves to the next arm, an
external system. The closure statement, when earned, reads: *for root R,
three consecutive independent blind reconstructions produced distinct
implementations satisfying R; each passed the complete conformance gate and
itself executed the pinned reconstruction operation; no counterexample from
the three trials required modification of R.*

The ratchet optimizes a second objective at the same time, and the two pull
against each other: the boundary must stay regrowable within the declared
`usd` envelope. Every counterexample adopted hardens the specification and
raises the going rate for a rebuild. A boundary can be too sharp to land
within budget, and the failed 40-turn gpt-5 kernel attempt is the witness, so
sharpening stops when either the counterexamples dry up or the going rate
reaches the envelope, whichever comes first.

Making this stopping rule an executable gate would itself be an
identity-bearing change, since it would live in a pinned suite. Until then it
is stated here as procedure.

## Declaring the shape of an expected divergence

A transition that deliberately changes pinned reference data owes the
receiver more than "the digests will differ". It owes the shape of the
difference, stated so that a tool can hold the new data to it. The witness is
the APEIRON campaign's A66 fix, where two warmup-evaluation rows were added
at the head of one series with values identical everywhere, and a global step
counter turned that into near-total digest divergence, twice costing a full
reference regeneration
(`research/proposals/2026-11-02-apeiron-campaign-feedback.md`, item 3).

`reticuli.divergence` is the comparator. The transition's provenance note
ships a declaration naming which series, which class (`prefix-added`,
`rows-inserted`, `value-change`), the join under which everything else must
still match exactly, and any field a relabeled counter excuses. The receiver
then verifies:

    python3 -m reticuli.divergence original.csv revised.csv declaration.json

Rows outside the declared shape are refused, with the first offending row
named. A series the declaration does not cover must be identical, and a
series present on one side only is refused. The verdict replaces the flat
digest mismatch the receiver would otherwise re-derive by hand. It does not
replace the digest itself, which still pins the data the claim actually
shipped.

## A worked example

The first transition done by this procedure was corrective. On 2026-09-18 the
recipe still declared a produce step for `src/reticuli/inspect.py`, a module
deleted when `inspect` was retired into audit's strict default. Removing the
phantom step moved the root from `5c81c5b5` to `3ad6e0cc`. It was an internal
click, so it took a reseal, the gate, a fresh audit receipt, the recorded
pair
([`research/provenance/revision-2026-09-18-repo-phantom-step.md`](https://github.com/rz4/reticuli/blob/main/research/provenance/revision-2026-09-18-repo-phantom-step.md)),
and a room refresh, deliberately unsigned. The six layer roots held, because
the phantom lived only in the top-level recipe. That is the whole procedure
at its smallest: a one-line boundary correction carried through every step.
