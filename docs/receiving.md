# Receiving a claim

Someone sends you a directory, or a tar, and says their code works. This page
is about what you do with that.

## One command

```
$ ret audit theirclaim
```

It re-runs their gates in the STRICT sandbox — writes confined, network
denied, and your own files masked, because a stranger's gate should not get
to read your home directory while you judge their claim. It does not read a
stored verdict. Silence and exit 0 means every verdict was re-earned here;
a failure is one stderr line naming the gate. Then the account of what you
are now trusting, instantly:

```
$ ret status --all theirclaim
```

If they sent a tar:

```
$ ret import theirclaim.tar ./theirclaim && ret audit ./theirclaim
```

## Reading the output

Four blocks — what is fixed, what is free, what was demonstrated here, what
remains unknown. The demonstrated block is the one you are trusting:

```
identity    ok        the bytes present hash to the sealed root
gates       earned    1 re-run here, sandboxed: TOML_OK=ok
proof       recorded  a recorded three-machine crosscheck
signatures  none      no trust anchor configured
```

**identity** — the files present hash to the root the sender named. If this
says `MISMATCH`, something changed after sealing: the claim you are holding is
not the claim they described. It might be innocent (a formatter ran over a
pinned file) and it is still a different claim.

**gates** — the acceptance tests ran *here*, on *your* machine, in a sandbox,
and their pinned outputs reproduced. This is the line that means something. A
claim can show `identity ok` and `gates not earned`, which says the bytes are
intact but the thing does not actually work here — a missing dependency, a
platform difference, a test that never really passed.

Watch for the inverse too: if identity fails, a *passing* gate earns nothing,
because the thing being judged is not the thing that was sealed. The report
says so in that case rather than showing a reassuring green.

**proof** — a recorded three-machine crosscheck: the sender ran it on the
original, a byte copy, and an independent rebuild. It is evidence they are
passing along, not something you verified; the machines are gone. Treat it as
a claim about history.

**signatures** — whether anyone you trust vouched for this. With no
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
