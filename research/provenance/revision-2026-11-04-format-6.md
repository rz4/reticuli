# revision 2026-11-04 — format 6: identity determines acceptance

    8e4e637213d045177813113a76cd071c0003b2080859e42a1b92e93c26cdd19f
 -> f419e409dfaada9d0eba77014aac51853193421eebe2521b39f0ba9d682937b1

*An identity-bearing transition. Three findings from two outside reviews,
each reproduced before being acted on, each recorded in
`research/audits/`: `2026-11-04-identity-semantics.md` and
`2026-11-04-envelope-finiteness.md`.*

## Why identity had to move

The root is supposed to name an equivalence class of implementations that
pass. That requires everything the identity function discards to be incapable
of changing whether a realization is accepted:

    root(C1) == root(C2)  =>  audit(C1, E) == audit(C2, E)

Two discarded things could change it, and both were measured doing so.

**Step order.** Format 4 sorts the step list into the preimage on the stated
ground that order is authoring form. Gates execute in file order in one
shared workspace and gate outputs are never materialized into a room, so a
gate reading what an earlier gate wrote makes order decide. Two claims
differing only in that order sealed to one root — `42909c24…` — with one
auditing `earned` and the other `failed`.

**File mode.** `build_digest` committed path and content and not the mode, so
`chmod 644` on a generated program left the digest byte-identical while the
cold audit went to `Permission denied`.

Neither was one implementation's bug. `reticuli.reference`, kept
deliberately independent so the two must agree, computed the same roots and
the same digests throughout. The implementations agreed perfectly and were
wrong together, which placed the defect in `spec/identity.md`. A conformance
vector proves two implementations compute one hash; it cannot prove the hash
identifies the acceptance predicate.

## What moved

**Format 6 stops sorting the step list.** Order is in the preimage, so two
orderings are two claims — which is what they always were. Vectors
`v16-format6-order-a` and `-b` pin it with *different* `expected-root`
values, the exact inverse of what the format-4 pair pins.

**Format 6 commits the owner-execute bit** into `build_digest`, as a third
element `"x"` or `"-"`. One bit only: read and write are the operator's
business, execute is the claim's. Vector `v17-format6-exec-bit` pins the
triple form.

**Formats 4 and 5 are protected by a refusal, not a repair.** A root sealed
under them must keep verifying, so they keep sorting, and
`recipe._refuse_ordered_gates` now refuses at parse a format-4/5 recipe whose
gate command names an output an earlier gate declares. Sound but incomplete —
it reads commands, and a command can reach a file through a variable or a
script — and `spec/claim-format.md` states that limit rather than implying
coverage it does not have.

**A declared cost ceiling must be finite.** TOML admits `inf` and `nan`, and
the crosscheck compares `paid <= ceiling`, so `usd = inf` published a hard
budget that bound nothing and `usd = nan` published one nothing could meet.
Finiteness was already required of a record's cost value, of a measured cost,
and of `tolerance` and `mutation_floor` thirty lines below in the same
function — the last added 2026-10-29 under a comment naming the envelope as
the exemplar it was modelled on. It was the exemplar for type and sign; the
copy added finiteness and nobody came back.

## Three mode-dropping copies, fixed outside identity

Not identity-bearing, and fixed in the same transition because the new vector
made them impossible to ignore:

| site | was | now |
|---|---|---|
| `transfer.export` | header forced `0o644` | 755 or 644, derived from the source, still deterministic |
| `transfer._extract` | ignored the member mode | honours the execute bit |
| `_util.copy_into` | `copyfile` only | carries the mode, as `_kernel.core._copy_into` already did |
| `scripts/selfclaim` | `copyfile` only | carries the mode |

The consequence of the first two was larger than a permissions nit: the
two-directory `ret crosscheck` materializes its byte-copy leg through
export/import, so it **rejected for any claim whose output must be
executable** — the invocation `docs/make-a-claim.md` showed annotated
`# silent exit 0`. It accepts now.

`v17-format6-exec-bit` found the fourth site by itself: the chain builder
staged it with `copyfile`, and the vector's own expected digest "drifted"
against a copy that had lost exactly the bit the vector exists to pin.

## The ritual

1. **Add** — the above.
2. **Reseal** — `8e4e6372` → `f419e409`.
3. **Re-earn** — `python3 gate.py`, cold: `repo-ok`, all criteria. Two deaths
   on the way, both the documented shape of a format bump: `core_check`'s
   `FORMAT` seam (5 → 6), and the self-claim layer pins. `core` moved because
   its criterion changed; `reference` moved because it pins the vectors and
   the set gained three. The other eighteen layers held, which is the
   structure reporting honestly — a layer root pins its check, not the
   implementation beneath it, and `identity`, `recipe` and `reference` all
   changed underneath without their boundaries moving.
4. **Reprove** — see below. Not met at this root.
5. **Record** — this file.
6. **Resign** — the keyholder signs; no agent signs.
7. **Refresh the room** — `room/reticuli` re-exported at the new root.

The zeta population registry was rebuilt and reports one current-root member:
membership is never inherited across a root move, so the standing population
retired exactly as the protocol requires.

## What this transition does NOT claim

**The count is 0 of 3 at `f419e409`**, as it was at `8e4e6372`. No succession
trial has been run against this boundary. By condition 7 this adopted change
resets the count, which is the ratchet charging its intended cost.

**Formats 4 and 5 remain unsound for a recipe with a hidden ordering
dependency.** The refusal catches the written shape, not every shape, and no
root is withdrawn — withdrawing roots is not something this format does.

**The authorization consequence of the mode gap was never tested end to
end.** `phase()` decides `signed` from root, proof and signature and
re-executes no gate; with the digest now moving on `chmod`, a mode change
stales a signature honestly. That chain is verified at every link except the
ceremony itself.
