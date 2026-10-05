# Transitions — how a reticuli claim changes

*Informational — the procedure for changing a claim's identity. The pinned
inputs it governs are defined in [`spec/`](../spec/) and `reticuli.toml`; see
also [`GOVERNANCE.md`](../GOVERNANCE.md).*

Reticuli's own development is reticuli's protocol applied to itself. A change
that touches the boundary is not an edit; it is a new claim. This document is
the procedure for making one — the same ritual whether the hand on the crank
is a maintainer today or an outside operator once the call is open.

The change is monotonic: a new root supersedes the old, it does not amend it.
Roots only move forward, and the room (`room/reticuli`, the blind export)
tracks the latest.

## Two kinds of change

- **Ordinary** — the implementation under `src/` (generated, excluded from the
  root), `tests/`, `docs/`, `research/`, tooling. These do not move the root.
  Normal review; nothing on this page applies.
- **Identity-bearing** — anything that edits a pinned input: the recipe
  (`reticuli.toml`), `spec/`, or an acceptance suite under `criteria/`. These
  move the root and follow the ritual below.

How to tell which you are making: the recipe's `[claim].inputs` list and its
non-generated produce steps are the pinned set. When in doubt, make the change
and run `ret verify .` — if the root moved, it was identity-bearing, and a
moved root that you did not intend is a mistake to undo, not to reseal.

## The ritual: add → reseal → reprove → resign

The mnemonic is four verbs; the full checklist is seven steps.

1. **Add.** Make the boundary change, and state *why* identity must move. A
   moved root is a stronger or more correct claim — never an accident, never
   incidental cleanup.
2. **Reseal.** Recompute the root and write the new manifest:
   `python3 -c "import sys; sys.path.insert(0,'src'); from reticuli import kernel; kernel.seal('.')"`
3. **Re-earn.** Run the gate cold — `python3 gate.py` — so the reference passes
   at the new root, then `ret audit .` to leave a fresh receipt.
4. **Reprove.** An independent blind rebuild from the new boundary. How strong
   this must be depends on the change — see the accept bars below.
5. **Record.** Write the old→new pair in `research/provenance/` as a
   `revision-*.md`, saying what moved and why the root moved with it.
6. **Resign.** A keyholder signs the new root when the change warrants it — see
   the bars. **No agent signs**; the signature is the human trust boundary.
7. **Refresh the room.** Re-export the blind boundary so `room/reticuli` names
   the new root (`ret export . room.tar --blind`, then commit the tree onto the
   room branch).

## The accept bars — how strong the reprove and the signature must be

Not every click deserves a paid rebuild or a signature. The bar scales with
what the change claims.

- **Internal click** — a maintainer correction or hardening. Bar: reseal +
  gate + recorded old→new pair. Blind reproduction is reserved for testing the
  fixpoint (below), not spent on every click. Not signed — the signature is the
  ceremony, not a per-commit stamp.
- **External transition** — an operator's submission once the call is open.
  Bar: a **blind, any-producer** rebuild that lands the root, to *accept* the
  transition. A routine hardening PR must not cost a paid vendor session.
- **Version stamp / completion** — blessing a root as a released version. Bar:
  the full paid ladder against the best independent blind reproduction, then
  the keyholder signs. This is the ceremony that turns a stable root into a
  version.

## The fixpoint — when the ratchet rests

The boundary is stable when **k consecutive independent blind reproductions
land the root with zero adopted counterexamples.** That is the stopping rule
for calling a root "very stable" rather than merely "current."

**k = 3**, set by the keyholder 2026-10-05, with the qualifying conditions
spelled out so a trial either counts or does not:

1. The root is frozen before the trial; only the blind boundary is given.
2. The producer is independent and the implementation genuinely distinct.
3. The full conformance gate establishes membership — `gate.py`,
   `ret verify`, `ret crosscheck` — not a sampled subset.
4. **The recursive step**: the reconstructed implementation itself performs
   the pinned reconstruction operation — through its own CLI, from a blind
   room, landing that claim's root. A tree that passes every suite but
   cannot reconstruct is a decoy, not a member (witnessed: the r4 tree,
   refused for exactly this).
5. At least one of the three trials re-earns on a machine and operator
   outside the generation environment, with record, cost, producer
   declaration, and provenance sealed.
6. All three land within the declared `usd` envelope.
7. The three trials span at least two model families, and **no boundary
   change intervenes** — an adopted counterexample resets the count to
   zero, which is the point: the count only grows while the boundary has
   stopped learning.

Closure of the reticuli→reticuli arm is exactly this bar met. Closed does
not mean finished — it means the first-order question is answered (the
boundary transports enough to re-realize the tool, reconstruction
operation included), and research effort moves to the next arm: an
external system. The closure statement, when earned, reads: *for root R,
three consecutive independent blind reconstructions produced distinct
implementations satisfying R; each passed the complete conformance gate
and itself executed the pinned reconstruction operation; no counterexample
from the three trials required modification of R.*

There is a second objective the ratchet optimizes at the same time, and the
two pull against each other: the boundary must stay **regrowable within the
declared `usd` envelope**. Every counterexample you adopt hardens the spec and
raises the going rate for a rebuild. A boundary can be too sharp to land within
budget — the failed 40-turn gpt-5 kernel attempt is the witness — so
sharpening stops when either the counterexamples dry up or the going rate
reaches the envelope, whichever comes first.

(Making this stopping rule an *executable* gate would itself be an
identity-bearing change, since it would live in a pinned suite. It is stated
here as procedure until then.)

## A worked example

The first transition done by this procedure was corrective. On 2026-09-18 the
recipe still declared a produce step for `src/reticuli/inspect.py`, a module
deleted when `inspect` was retired into audit's strict default. Removing the
phantom step moved the root `5c81c5b5 → 3ad6e0cc`. It was an internal click:
reseal + gate + a fresh audit receipt + the recorded pair
([`research/provenance/revision-2026-09-18-repo-phantom-step.md`](../research/provenance/revision-2026-09-18-repo-phantom-step.md))
+ a room refresh, deliberately unsigned. The six layer roots held, because the
phantom lived only in the top-level recipe. That is the whole ritual at its
smallest — a one-line boundary correction carried through every step.
