# Receiving a claim

*Informational — an operational guide. The normative contract is in [`spec/`](https://github.com/rz4/reticuli/tree/main/spec/).*

Someone sends you a directory, or a tar, and says their code works. This page
is about what you do with that.

## One command

```
$ ret audit theirclaim
```

This re-runs their gates in the strict sandbox, with writes confined, the
network denied, and your own files masked, because a stranger's gate should
not get to read your home directory while you judge their claim. It does not
read a stored verdict. Exit 0 means every verdict was re-earned here; in a
terminal you also get a one-line `audit: earned …` on stderr, while piped or
in CI it stays silent and the exit code is the answer. A failure is one
stderr line naming the gate. For the account of what you are now trusting:

```
$ ret status theirclaim
```

`ret status --all` adds the exhaustive per-file ledger, while the plain form
is the one-screen account.

If they sent a tar:

```
$ ret import theirclaim.tar ./theirclaim && ret audit ./theirclaim
```

## Reading the output

`identity` and `audited` are what you are trusting. The rest is context: how
hard the tests are, what the sender passed along, and who vouched.

```
claim      theirclaim
root       a82b7d25ac3f…
identity   fresh
audited    2026-…Z on this machine
deciding   mutation 0.90 (10 mutants)
proof      recorded
signed     none

next  earn it here: ret audit .
```

**identity** — `fresh` means the files present hash to the root the sender
named. If it says `broken`, something changed after sealing, and the claim
you are holding is not the claim they described. The cause may be innocent, a
formatter run over a pinned file for instance, and it is still a different
claim. `ret verify` names the moved files.

**audited** — the acceptance tests ran here, on your machine, in a sandbox,
and their pinned outputs reproduced, with the date showing when. This is the
line that means something. `never on this machine` says the bytes are intact
but nothing has been re-earned here yet, so run `ret audit`. A claim can be
`fresh` and still fail to audit, through a missing dependency, a platform
difference, or a test that never really passed.

Watch for the inverse too. If identity is `broken`, a passing gate earns
nothing, because the thing being judged is not the thing that was sealed.
`ret audit` refuses in that case rather than showing a reassuring green.

**deciding** — how hard the tests are, from `ret assess`. A mutation rate is
how many injected faults they caught. A high `identity` and `audited` with a
low deciding number is a claim whose tests admit a lot, and should be read as
"this passes, but the check is thin."

**proof** — a recorded three-machine crosscheck, meaning the sender ran it on
the original, a byte copy, and an independent rebuild. It is evidence they
are passing along rather than something you verified, since the machines are
gone. Treat it as a claim about history.

**signed** — whether anyone you trust vouched for this. With no
`allowed_signers` file the answer is always that nothing is authorized to
you, which is correct rather than broken: trust is relative to your anchor,
and you have not named one.

## Checking a signature, and what an anchor buys

```
$ ret sign theirclaim --check                          # no anchor
$ ret sign theirclaim --check --signers ~/.ssh/my-anchor
```

Unanchored, the strongest verdict available is `intact`, meaning the
signature is self-consistent and valid for whatever key is embedded in it.
That says a statement was signed, not who signed it. The identity a row
prints comes from the statement's own bytes, which the signer wrote. So
`authorized` stays false and the check exits non-zero, with `anchored =
false` naming the reason. Nothing is authorized to you until you say who you
trust.

Anchored, the key that actually signed is checked against the identity you
named, and only then can the report say `authorized`. A statement re-signed
by any other key reads `invalid`.

Build the anchor yourself. A sender may publish their key, as this repository
publishes its keyholder's in [`SIGNERS`](https://github.com/rz4/reticuli/blob/main/SIGNERS),
but a key that travels with the signature it vouches for proves nothing on
its own, since whoever could forge one could ship the other. Confirm the
fingerprint through a channel that did not carry the claim, then build your
anchor from that channel rather than from the package. This repository's
[`SIGNERS`](https://github.com/rz4/reticuli/blob/main/SIGNERS) names where
its keyholder's key is published and gives the commands. The shape is:

```
$ curl -s https://api.github.com/users/<sender>/ssh_signing_keys   # out of band
$ ssh-keygen -lf ~/.ssh/my-anchor     # compare to the fingerprint they state
$ ret sign theirclaim --check --signers ~/.ssh/my-anchor
```

Whatever the channel, the test is the same: two independent sources must
state the same fingerprint, and only one of them may be the package you are
judging.

Two things a signature does not mean. It is authorization rather than proof,
and each row reports `proof_recorded` separately, where a `false` says no
crosscheck accompanied the ceremony. It also freezes an implementation,
because the signed statement covers the build digest as well as the root, so
a claim that was re-implemented — same root, same criteria, different
generated bytes — reports `chain_holds = false` until it is re-authorized.
That is the design working: identity floats above the implementation and
authorization does not.

## What it deliberately does not tell you

The second block of output is not boilerplate.

**A passing claim says nothing about the implementation.** The implementation
is outside the hash by design, which is what makes a claim an equivalence
class rather than a fingerprint. A backdoored implementation that passes the
tests verifies identically. If you need to know that a specific artifact is
the one somebody reviewed, you want the build digest and a signature over it.

**A passing claim says nothing about how good the tests are.** That is a
separate measurement:

```
$ ret assess theirclaim
```

It reports mutation adequacy, whether the gate is decided by generated code,
and, if you are willing to spend on it, whether an independent model can
reconstruct the implementation from the tests alone. The measurements stay
with the claim as store residue, stamped with the root they measured, and
from then on `ret status --all` shows them as the claim's **deciding**
evidence instead of its "strength unknown" line, until a criterion moves and
the evidence goes stale with it. See
[`examples/weak/`](https://github.com/rz4/reticuli/blob/main/examples/weak/README.md)
for a claim that passes everything above and is still nearly worthless, and
why.

## What you are trusting, concretely

- **The criteria.** The pinned test files are the specification. Read them.
  Everything else in this system is machinery for making sure those files
  were really what ran.
- **Your machine and this tool.** The gates execute code the sender wrote.
  `ret audit` runs them under the strict jail by default, with writes
  confined to the workspace, the network denied, and your own files masked
  from the stranger's code, and `--no-strict` opts down. That holds where the
  platform has a sandbox at all, which is reported honestly when it does not.
  A gate is still code you chose to run.

Full boundaries are in [`docs/threat-model.md`](threat-model.md).

## If you want to check it yourself, without this tool

The identity computation is specified in
[`spec/identity.md`](https://github.com/rz4/reticuli/blob/main/spec/identity.md)
precisely enough to reimplement, and this repository ships a second
implementation of it (`reticuli.reference`) kept deliberately independent of
the kernel so the two have to agree. You do not have to take the kernel's
word for a hash.

You do not have to take the spec's word for your reimplementation either.
[`spec/vectors/`](https://github.com/rz4/reticuli/blob/main/spec/vectors/README.md)
holds conformance vectors — tiny claims with their expected roots and build
digests — and a runner that points any implementation, in any language, at
them. Reproduce every expected value and you conform; miss one and the vector
names which rule you got wrong.
