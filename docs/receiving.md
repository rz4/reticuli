# Receiving a claim

Someone sends you a directory, or a tar, and says their code works. This page
is about what you do with that.

## One command

```
$ ret inspect theirclaim
```

It re-runs the gates in a sandbox — it does not read a stored verdict — and
prints three things: what holds, what this does not establish, and what you
are trusting. Exit status is 0 only if identity and gates both hold.

If they sent a tar:

```
$ ret import theirclaim.tar ./theirclaim && ret inspect ./theirclaim
```

## Reading the output

```
   what holds here
0  identity     ok        the bytes present hash to the sealed root
1  gates        earned    1 re-run here, sandboxed: TOML_OK=ok
2  proof        recorded  a recorded three-machine crosscheck
3  signatures   none      no trust anchor configured
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
can reconstruct the implementation from the tests alone. See
[`examples/weak/`](../examples/weak/README.md) for a claim that passes
everything above and is still nearly worthless, and why.

## What you are trusting, concretely

- **The criteria.** The pinned test files *are* the specification. Read them.
  Everything else in this system is machinery for making sure those files were
  really what ran.
- **Your machine and this tool.** The gates execute code the sender wrote.
  They run sandboxed where the platform supports it (macOS seatbelt, Linux
  bubblewrap, probed functionally, reported honestly when absent) — but a gate
  is still code you chose to run.

Full boundaries: [`docs/threat-model.md`](threat-model.md).

## If you want to check it yourself, without this tool

The identity computation is specified in
[`spec/identity.md`](../spec/identity.md) precisely enough to reimplement, and
this repository ships a second implementation of it
(`conformance/reference_seal.py`) kept deliberately independent of the kernel
so the two must agree. You do not have to take the kernel's word for a hash.
