# Open call: regrow Reticuli from its tests alone

This repository is a claim about itself — its current root is named in
the room's manifest (`git show room/reticuli:.reticuli/manifest.json`) — an
equivalence class of programs: every implementation of the whole tool that
passes its nine acceptance suites on its pinned specification and vectors.
This is a standing invitation to produce another member, by any producer you
choose, from the frozen boundary alone, and to have this repository's own
machinery verify it.

## The two rungs

**The kernel** is the tractable entry, and it is proven regrowable: two
members were written by different vendors' models, and a blind agent has
since regrown `reticuli/kernel.py` from its suite alone in a distinctly
different shape, landing the same root. Start here to feel the loop:
`ret export examples/kernel room.tar --blind` gives you the recipe, the
1,900-line suite, the pinned verdict, and the manifest — no implementation.
Write `reticuli/kernel.py` from the suite until `python3
checks/kernel_check.py` passes under both host conditions (bare, and with
`RETICULI_JAILED=1`).

**The whole tool** is the frontier. The branch `room/reticuli` is
the blind workspace for all of Reticuli: the recipe, the specification, the
nine suites, `gate.py`, `selfclaim.py`, and the conformance vectors — every
deciding input, and no `src/` implementation.

```
git fetch origin room/reticuli
git worktree add ../reticuli-room room/reticuli
```

(Equivalently: `ret export . room.tar --blind` from a checkout produces the
same bytes.) Regrow all of `src/reticuli/` there, from the boundary alone,
until `python3 gate.py` passes — which means every layer's suite, the
self-hosting chain rebuild, and the conformance vectors, all green — and the
directory verifies at the target root. The suites' docstrings specify the
exact byte-level serializations; `spec/vectors/` holds the same values as
runnable conformance data. This is a large reconstruction; partial progress
and a recorded failure are themselves welcome evidence.

The boundary now pins the fixpoint itself: `self_check`'s bootstrap section drives a rebuilt reticuli through its own command line to rebuild a claim from a blind room and land its root. A conforming reticuli is therefore not just a judge but a rebuilder — a regrown reticuli can itself regrow.

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
| v2.2 suite (1,570 lines) | gpt-5, resumed across host kills | passed: 4,575,703 tokens, $25.74 ledgered (understated — two killed sessions unrecorded) |
| v2.4 suite (this one, ~1,900 lines) | gpt-5, shipped producer, 40-turn cap | **did not land**: 4,334,578 tokens, $24.38, near-miss (a 1,076-line kernel failing a confinement rule; turn-bound). [Detail.](provenance/attempt-2026-09-18-gpt5-v2.4-kernel.md) |
| v2.4 suite | a blind Claude agent, open iteration | landed the same day, 1,190 lines, distinct shape — proof of regrowability, not a paid three-machine proof |

The claim now declares `envelope = { usd = 40.0 }`, pinned from the
ledger history above with honest headroom. It is a hard condition: a redo
measured over the ceiling is rejected, and a proof that never measured
dollars is incomplete, never accepted.

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
pin — finding 13 was exactly such a divergence, and this suite now pins it.

## The call's own record

The call is open when a signed record of the claim sits beside this
document at `research/open-call/reticuli.record.json` — its `when` field is the
publication date your producer's cutoff is compared against, and a call
cannot be anonymous because a record cannot be unsigned. Signing is the
keyholder's act, performed once:

```
ssh-keygen -t ed25519 -f ~/.ssh/reticuli_signing -C "rzamoraresendiz@lbl.gov"
PYTHONPATH=src python3 -m reticuli record . \
    -o research/open-call/reticuli.record.json --key ~/.ssh/reticuli_signing
git add research/open-call && git commit
git push origin main room/reticuli
```
