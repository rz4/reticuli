# Proposal — a signature says how deep it looked

*Staged 2026-10-09, from the instrument sweep that followed the batched
pins — the second instrument-found seam of the day. A design decision
first, then (depending on the choice) a criteria edit in the exchange
layer; staged for the keyholder. Witness measured before staging.*

## The finding

`attest.sign` promises to sign "only claims whose verdicts reproduce
from the claim's own bytes" and re-earns exactly `kernel.audit` — the
SHALLOW gate. That half is pinned: exchange_check asserts sign refuses a
claim whose own verdicts fail. The DEEP half is unexercised, and it
bites where it matters most — at the human trust boundary:

    composed claim, component code forged
    (its own gate blind by construction):
      kernel.audit:        True
      registry.audit_deep: False     (the composed verdict refuses — pinned)
      attest.sign:         SIGNS     (measured 2026-10-09)

The keyholder's signature endorses a claim that its own deep audit
refuses, and `sign_root` folds the component roots into the signed chain
identity — a signature over a DAG whose layers were never re-earned at
the ceremony. GATES COMPOSE, VERDICTS NEVER CARRY — except here, where
the strongest verdict in the system (the signed one) quietly carries the
shallow result across the composed boundary.

The mitigating fact, stated honestly: this is DOCUMENTED behavior
("kernel.audit" is named in the docstring), and `review_packet` shows
the keyholder the component chain plus a fresh shallow audit. The gap is
not deception; it is that the signed STATEMENT does not say which depth
was earned, so a reader of the signature cannot distinguish "this layer
verified" from "this chain verified."

## The design decision (the keyholder's, not an agent's)

Three shapes, in increasing strength:

1. **The statement names its depth.** The signed statement records
   `depth: own-gates` or `depth: composed`, and `check` surfaces it. No
   behavior change; the signature stops overclaiming. Cheapest; honest.
2. **Deep by default for composed claims.** `sign` re-earns
   `audit_deep` whenever the manifest declares components, with a
   documented opt-down to shallow that the statement records. Costs a
   deep audit per ceremony on composed claims (the repo's own chain:
   ~25 minutes warm-cache-free; the verdict cache makes this cheap
   after the first earn).
3. **Deep always, no opt-down.** Strongest; makes signing the repo
   expensive and is probably over-strong for leaf claims (no
   components → deep == shallow anyway).

The criterion, once chosen, is one fixture in exchange_check: the
witness above, asserting either refusal (shapes 2–3) or a statement that
names its shallow depth (shape 1).

## Status

STAGED. Not landed; the shape choice is the keyholder's. If shape 2 or 3
is chosen, the change lands as criteria + attest fix together, and by
the ratchet rule resets the count — one more candidate for the NEXT
batched boundary move alongside the pull-closure design decision
(future-pin-copy-compactness), so the count resets once more at most.

## Addendum, same day — records share the gap

`record.emit` re-earns `kernel.audit` (shallow) too, so the one document
other programs may parse also carries an unstated depth. Whatever shape
the keyholder chooses should cover both emitters: the signed statement
AND the record name the depth they earned (`own-gates` vs `composed`),
or both go deep on composed claims. One decision, two surfaces, one
fixture each.

## Status (final)

SIGNED ("pin these as well") and LANDED 2026-10-09 in the endorsement
batch, root c48fbf52 -> 57da3b61, as shape 2 narrowed to its honest
core: AN ENDORSEMENT COMPOSES — sign re-earns audit_deep on claims that
declare components; record.emit deliberately keeps its per-claim
semantics (a record states, a signature endorses). Provenance:
revision-2026-10-09-the-endorsement-batch.md.
