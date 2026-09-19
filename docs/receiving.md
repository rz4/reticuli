# Receiving a claim

*Informational — an operational guide. The normative contract is in [`spec/`](../spec/).*

Someone sends you a directory, or a tar, and says their code works. This page
is about what you do with that.

## One command

```
$ ret audit theirclaim
```

It re-runs their gates in the STRICT sandbox — writes confined, network
denied, and your own files masked, because a stranger's gate should not get
to read your home directory while you judge their claim. It does not read a
stored verdict. Exit 0 means every verdict was re-earned here — in a terminal
you also get a one-line `audit: earned …` on stderr; piped or in CI it stays
silent and the exit code is the answer. A failure is one stderr line naming the
gate. Then the account of what you are now trusting, instantly:

```
$ ret status theirclaim
```

(`ret status --all` adds the exhaustive per-file ledger; the plain form is the
one-screen account.)

If they sent a tar:

```
$ ret import theirclaim.tar ./theirclaim && ret audit ./theirclaim
```

## Reading the output

The one-screen account. `identity` and `audited` are what you are trusting; the
rest is context — how hard the tests are, what the sender passed along, who
vouched:

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
named. If it says `broken`, something changed after sealing: the claim you are
holding is not the claim they described. It might be innocent (a formatter ran
over a pinned file) and it is still a different claim; `ret verify` names the
moved files.

**audited** — the acceptance tests ran *here*, on *your* machine, in a sandbox,
and their pinned outputs reproduced (the date is when). This is the line that
means something. `never on this machine` says the bytes are intact but nothing
has been re-earned here yet — run `ret audit`. A claim can be `fresh` and still
fail to audit: a missing dependency, a platform difference, a test that never
really passed.

Watch for the inverse too: if identity is `broken`, a *passing* gate earns
nothing, because the thing being judged is not the thing that was sealed.
`ret audit` refuses in that case rather than showing a reassuring green.

**deciding** — how hard the tests are, from `ret assess`: a mutation rate is
how many injected faults they caught. A high `identity`/`audited` with a low
deciding number is a claim whose tests admit a lot — read it as "this passes,
but the check is thin."

**proof** — a recorded three-machine crosscheck: the sender ran it on the
original, a byte copy, and an independent rebuild. It is evidence they are
passing along, not something you verified; the machines are gone. Treat it as
a claim about history.

**signed** — whether anyone you trust vouched for this. With no
`allowed_signers` file, the answer is always "nothing is authorized to you",
which is correct rather than broken: trust is relative to *your* anchor, and
you have not named one.

## What it deliberately does not tell you

The second block of output is not boilerplate. In particular:

**A passing claim says nothing about the implementation.** The implementation
is outside the hash by design — that is what makes a claim an equivalence
class rather than a fingerprint. A backdoored implementation that passes the
tests verifies identically. If you need to know that a specific artifact is
the one somebody reviewed, you want the build digest and a signature over it.

**A passing claim says nothing about how good the tests are.** That is a
separate measurement:

```
$ ret assess theirclaim
```

which reports mutation adequacy, whether the gate is decided by generated
code, and — if you are willing to spend on it — whether an independent model
can reconstruct the implementation from the tests alone. The measurements
stay with the claim as store residue, stamped with the root they measured:
from then on `ret status --all` shows them as the claim's **deciding**
evidence instead of its "strength unknown" line, until a criterion moves
and the evidence goes stale with it. See
[`examples/weak/`](../examples/weak/README.md) for a claim that passes
everything above and is still nearly worthless, and why.

## What you are trusting, concretely

- **The criteria.** The pinned test files *are* the specification. Read them.
  Everything else in this system is machinery for making sure those files were
  really what ran.
- **Your machine and this tool.** The gates execute code the sender wrote.
  `ret audit` runs them under the strict jail by default — writes confined
  to the workspace, network denied, and your own files masked from the
  stranger's code (`--no-strict` opts down) — where the platform has a
  sandbox at all, which is reported honestly when absent. A gate is still
  code you chose to run.

Full boundaries: [`docs/threat-model.md`](threat-model.md).

## If you want to check it yourself, without this tool

The identity computation is specified in
[`spec/identity.md`](../spec/identity.md) precisely enough to reimplement, and
this repository ships a second implementation of it
(`reticuli.reference`) kept deliberately independent of the kernel
so the two must agree. You do not have to take the kernel's word for a hash.

And you do not have to take the spec's word for your reimplementation:
[`spec/vectors/`](../spec/vectors/README.md) holds conformance vectors —
tiny claims with their expected roots and build digests — and a runner that
points any implementation, in any language, at them. Reproduce every
expected value and you conform; miss one and the vector names which rule you
got wrong.
