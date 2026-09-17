# Open call: regrow the kernel from its tests alone

This repository's kernel claim — root
`e650b524528ff3b821e48099c818f2de24d0da60a70e27dc120752da7f60e2df` — is an
equivalence class of programs: every implementation that passes its
1,570-line acceptance suite on its pinned data. Two members exist today,
written by different hands. This is a standing invitation to produce a
third, by any producer you choose, and to have this repository's own
machinery verify it.

## The room

The branch `room/kernel-e650b524` is a blind workspace: the recipe, the
suite, the pinned verdict, and the manifest naming the target root — no
implementation.

```
git fetch origin room/kernel-e650b524
git worktree add ../kernel-room room/kernel-e650b524
```

(Equivalently: `ret export examples/kernel room.tar --blind` from a
checkout produces the same bytes.) Write `reticuli/__init__.py` and
`reticuli/kernel.py` there, from the suite alone, until
`python3 checks/kernel_check.py` passes under both host conditions — bare,
and with `RETICULI_JAILED=1` — and the directory verifies at the target
root. The suite's docstrings specify the exact byte-level serializations;
`spec/vectors/` holds the same values as runnable conformance data.

**Blindness is procedural, and we say so.** The two existing
implementations are one checkout away on this branch's sibling, and models
train on public code. The call asks you not to look, and asks you to
declare what you used: producer vendor, model, and the model's
training-data cutoff. This claim's room was first published on the date in
the signed record beside this document — a producer whose cutoff predates
it could not have memorized it. Declarations are recorded as declarations,
never as proof; that is this project's standing position on independence.

## The going rate

Honest numbers from this repository's own ledger, so you can budget:

| attempt | producer | outcome |
|---|---|---|
| v2.1 suite (1,351 lines) | gpt-5, environment matrix | passed first try: 12 min, 603,930 tokens, $3.40 |
| v2.2 suite (this one) | gpt-5, resumed across host kills | passed: 4,575,703 tokens, $25.74 ledgered (understated — two killed sessions unrecorded) |

The claim does not yet pin an envelope — `[claim] envelope` exists in the
format, but adding it to this claim is a revision and revisions orphan
proofs, so it waits for v2.3. Until then these measurements are the
guidance.

## Submitting

Open a pull request containing:

1. **Your claim directory** — the room plus your generated
   `reticuli/{__init__,kernel}.py`, sealed (`ret verify` fresh at the
   target root).
2. **Your record** — `ret record <your-claim> -o <name>.record.json --key
   <your-ssh-key>`, the one file other programs may parse
   (`spec/record.md`), signed in the `reticuli.record` namespace. State
   vendor, model, and cutoff in the pull request; a rebuild through
   `ret rebuild` ledgers the first two and your cost automatically.

This repository re-earns your verdicts itself — your gates are run here, on
your bytes, by CI and by hand; nothing is taken from testimony except what
is labeled testimony. A submission that crosschecks lands in the
provenance ledger with your record's digest and signer embedded in the
recorded proof. A submission that does **not** pass is welcome as evidence:
a failed attempt's ledger, without its bytes, documents either a hole in
the suite or a limit of the producer, and both are findings
(`docs/threat-model.md` lists the four causes; we have personally hit
three).

## What this is and is not

A third independent member strengthens the evidence that the tests alone
carry the software. It proves neither correctness nor independence — the
suite is the specification, and N-version evidence is evidence, not proof
(Knight and Leveson, and the threat model, in that order). The interesting
outcome is any of: a pass, a failure that names a suite gap, or a
divergence between your kernel and ours on a behavior the suite does not
pin — finding 13 was exactly such a divergence, and it is queued for the
next revision.

## The call's own record

The call is open when a signed record of the claim sits beside this
document at `docs/open-call/kernel.record.json` — its `when` field is the
publication date your producer's cutoff is compared against, and a call
cannot be anonymous because a record cannot be unsigned. Signing is the
keyholder's act, performed once:

```
ssh-keygen -t ed25519 -f ~/.ssh/reticuli_signing -C "rzamoraresendiz@lbl.gov"
PYTHONPATH=src python3 -m reticuli record examples/kernel \
    -o docs/open-call/kernel.record.json --key ~/.ssh/reticuli_signing
git add docs/open-call && git commit
git push origin main room/kernel-e650b524
```
