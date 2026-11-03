# Authorization requires an anchor: a defect found by walking a receiver's path

2026-11-03. The root moved

    37d860185e4f6343c5da8b1382a810b11d425924bdb6f169c52197c2e3f6afb0
    → b188d96bb703c2a1774dd910237f86fa2b8e32b015a02355c31d683a3e9c0611

and it moved because **the defect was pinned in the boundary**, not only
present in the implementation. That discovery is the substance of this
revision: the plan was an ordinary `src/` fix with the obligation staged for
later, and the cold gate refused it.

## How it was found

The keyholder signed `37d86018` and asked for the project to be made
*receivable*. Rather than assert receivability, the path a stranger walks was
executed: export the signed claim, import it into a clean directory, and run
the checks a receiver runs with the configuration a receiver has — which is
to say, **no trust anchor**, because `allowed_signers` is something a
receiver names and a sender cannot supply.

The repository's own fresh signature reported, to that stranger:

    anchored = false
    authorized = true
    verdict = intact    chain_holds = true    packet_holds = true
    exit 0

Then the obvious adversarial question: re-sign the statement with a key the
keyholder has never seen. Same output. `authorized = true`, exit 0, and the
identity `rzamoraresendiz@lbl.gov` printed as though verified — it is copied
from the statement's own bytes, which the signer wrote. **A receiver with no
anchor could not tell the keyholder's authorization from a forger's.**

## Why it survived

1. The per-row vocabulary was already correct: `intact` for
   `ssh-keygen -Y check-novalidate` (self-consistent, signer unknown),
   `authorized` only for `-Y verify` against a signers file. Only the
   aggregate `ok` conflated them, and the CLI renders that aggregate under
   the label `authorized`.
2. `docs/receiving.md` stated the doctrine correctly in prose — "with no
   `allowed_signers` file, the answer is always *nothing is authorized to
   you*" — while the tool said the opposite. Prose is not a gate.
3. **The criteria did not merely miss the receiver's configuration; they
   mandated the wrong answer in it.** `criteria/exchange_check.py` passes
   `signers=signers` on every call, so the unanchored path went unexercised.
   Worse, `criteria/surface_check.py` asserted

       code, out, err = _run2(["sign", m3, "--check"])
       assert code == 0 and out == "" and err == "", \
           "a verified authorization is silent"

   with **no signers file** — pinning that an unanchored check reports a
   verified authorization and exits silent. A conforming rebuild was
   therefore *required* to tell a receiver that a forged signature is
   authorized. This is the strongest possible form of the project's
   recurring coverage shape: the criterion exercised the configuration the
   author runs, and froze it as the boundary.

   It is also the reason this became a root move. The `src/` fix was
   written first and the cold gate refused it — `surface_check` and, through
   it, `self_check` both failed, naming "a verified authorization is
   silent." The boundary and the fix disagreed, and the boundary was wrong.

## What landed

- `attest.sign_check` requires `verdict == "authorized"` for a row to
  satisfy `ok`, and returns `anchored` so a reader knows why `authorized` is
  false. The CLI's existing refusal — "unauthorized — no authorization
  verifies against a trust anchor", with the `--signers` hint — now fires.
- `_r_sign_check` prints `anchored` beside `authorized`.
- `tests/test_sign_anchor.py` (8 tests) pins the four-case matrix: unanchored
  genuine and unanchored forged both `intact` and both not `ok`; anchored
  genuine `authorized`; anchored forged `invalid`. It also pins that an
  anchor naming a different identity does not authorize, that a swapped
  review packet refuses, and that an unsigned claim is not vacuously
  approved.
- `SIGNERS` publishes the keyholder's public key and fingerprint
  (`SHA256:CIcVyVTbkBFIat1Rxs0JleEWSXy8FMLGUvgJgYQVLgk`) with the warning
  that it is **not** the receiver's anchor: it travels with the signature it
  would vouch for, so it is useful only once its fingerprint is confirmed
  out of band. Unpinned, like README — distribution, not acceptance.
- `docs/receiving.md` gains the anchored-check section, the out-of-band
  fingerprint step, and the two things a signature does not mean.

## What moved in the boundary

- `criteria/surface_check.py` — the unanchored `--check` must now **refuse**,
  with a message naming the missing anchor; a verified authorization is
  silent only *with* `--signers`; and re-signing the statement with another
  key must fail an anchored check.
- `criteria/exchange_check.py` — the receiver's own configuration is
  exercised: unanchored is `intact` and not `ok`, a forged signature is
  asserted **indistinguishable** there (the criterion states the limit
  rather than pretending to detect it), anchored refuses the forgery, and
  the restored genuine signature authorizes again.
- `criteria/self_check.py` — the two layer roots that moved with their
  suites: `exchange` `918a7149 → 3b4125d6`, `surface` `ee4f556f → 9d8b9da2`.
  Nothing beneath them moved, which is the expected shape: this is a trust
  surface, not an identity rule.

## Why the signature needs renewing

Twice over. The signed statement covers `sign_root`, which folds the
**build digest** alongside the root — so a signature freezes an
implementation even though identity floats above one. This change edits
`src/`, which moves the digest; and it moves the root itself. The
2026-11-03 statement over `37d86018` is stale on both counts.

Worth stating plainly as a property of this project: **every `src/` commit
stales the signature**, because a signature here is a snapshot of
(criteria, implementation), not of criteria alone. A project under active
development cannot stay continuously signed, and should not pretend to.

Renewing is the keyholder's act:

    ret sign . --key ~/.ssh/reticuli-signing --as rzamoraresendiz@lbl.gov

## The lesson, kept

The fix was planned as ordinary and the gate promoted it to
identity-bearing. That sequence is worth preserving: a security property
believed to be "merely unpinned" turned out to be **pinned backwards**, and
nothing short of running the gate would have said so. The staged proposal
written an hour earlier
(`research/proposals/2026-11-03-pin-the-anchor-requirement.md`) argued for
adopting the obligation later, at a cost of one root move; it was wrong
about the starting position, and is marked accordingly.
