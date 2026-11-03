# A criterion should pin that authorization requires an anchor

> **LANDED 2026-11-03, same day, and for a reason this document got wrong.**
> Root `37d86018 → b188d96b`. The proposal below assumes the obligation was
> merely *absent* from the boundary and could be adopted later at leisure.
> It was not absent: `criteria/surface_check.py` asserted that an unanchored
> `sign --check` reports a verified authorization and exits silent, with no
> signers file — so the boundary **mandated** the defect, and a conforming
> rebuild was required to reproduce it. The cold gate refused the `src/` fix
> and said so, which is how this was discovered. There was no "later": the
> choice was correct the boundary or revert the fix.
>
> Landed as described under *The proposed obligation*, plus the
> `surface_check` correction the proposal did not know was needed. Account:
> `research/provenance/revision-2026-11-03-authorization-requires-an-anchor.md`.
> Preserved below as written, because a staged proposal that misread its own
> starting position is worth keeping legible.

2026-11-03. Staged, not landed. The implementation fix is already shipped
(ordinary change, no root move); this proposal is about whether the
*obligation* joins the boundary, which costs a root move and a re-signature.

## The measurement

Walking a receiver's path on this repository's own freshly signed claim:
`attest.sign_check`'s roll-up accepted an unanchored `intact` row as `ok`.
So a statement re-signed with a throwaway key the keyholder had never seen
reported

    anchored = false
    authorized = true
    verdict = intact      chain_holds = true      packet_holds = true
    exit 0

with the identity string `rzamoraresendiz@lbl.gov` printed as though
verified — it comes from the statement's own bytes, which the signer wrote.
A receiver with no anchor could not distinguish the keyholder's
authorization from anyone's.

Three things made this survivable for as long as it did:

1. The per-row vocabulary was already honest (`intact` for
   `check-novalidate`, `authorized` only for `ssh-keygen -Y verify` against
   a signers file). Only the aggregate conflated them.
2. `docs/receiving.md` had the doctrine right in prose — "with no
   `allowed_signers` file, the answer is always *nothing is authorized to
   you*" — while the tool said the opposite. Prose is not a gate.
3. **The one criterion covering this surface only ever exercised the
   anchored path.** `criteria/exchange_check.py` passes `signers=signers` on
   every call: it pins that a forged packet and a tampered signature refuse
   *with* an anchor, and never asks what happens without one. That is the
   recurring shape of this project's own coverage gaps — the criterion tests
   the configuration the author runs, not the one a stranger has.

## What shipped (no identity cost)

`sign_check` now requires `verdict == "authorized"` for a row to satisfy
`ok`, and reports `anchored` so a reader knows why `authorized` is false.
The CLI's existing refusal — "unauthorized — no authorization verifies
against a trust anchor", with the `--signers` hint — now actually fires.
`tests/test_sign_anchor.py` pins the four-case matrix:

| anchor | signature | verdict | ok |
|---|---|---|---|
| no | genuine | `intact` | false |
| no | forged | `intact` | false |
| yes | genuine | `authorized` | true |
| yes | forged | `invalid` | false |

plus two adjacent properties worth having pinned: an anchor naming a
different identity does not authorize (trust is per-identity, not
per-key-file), and a re-implemented claim reports `chain_holds = false`
until re-authorized (the signature freezes a build digest; identity floats
above the implementation, authorization does not).

## The proposed obligation

Extend `criteria/exchange_check.py` to exercise the **unanchored** path:
sign a fixture claim, re-sign the statement with a second key, and require
that neither the genuine nor the forged statement satisfies `ok` without a
signers file — while the anchored assertions it already makes stay
unchanged. Roughly fifteen lines in a battery that already builds signed
fixtures.

### Acceptance

- Unanchored `sign_check` on a genuinely signed claim: `ok` is false and
  the row reads `intact`.
- Unanchored `sign_check` on a statement re-signed by another key: `ok` is
  false, indistinguishable from the genuine row — the criterion asserts the
  indistinguishability rather than pretending it can be detected.
- Anchored, the keyholder's key authorizes and a stranger's reads `invalid`.

## The cost, stated plainly

`criteria/exchange_check.py` is a pinned input, so this moves the repository
root, which is the ordinary price of a strengthened criterion. The
unordinary price today: the root was signed on 2026-11-03, and a root move
invalidates that signature's `chain_holds` — so adopting this needs a
re-seal, a cold gate, a recorded pair, a room refresh, **and a keyholder
re-signature**. Batching it with the next identity-bearing change would pay
that ceremony once instead of twice.

Against the cost: an unpinned security property is one a rebuild may
silently drop, and this is the property that decides whether a receiver can
tell the keyholder from a forger. The boundary is the only place that
obligation survives a reimplementation, which is the whole argument for
pinning anything here.
