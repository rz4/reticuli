# The signing ceremony — prepared, not performed

## What is ready

The kernel claim (`conformance/kernel/`) is `sealed`, its gate re-earned, and its
three-machine proof recorded (`crosscheck-v21-2026-09-15.md`). This is the
**v2.1** claim — the revision that pinned seven measured under-specifications
— and its proof was re-earned against the revised suite, not inherited.

```
$ ret sign conformance/kernel                        # review only; no key, no signature
[review]
name         = "kernel"
root         = "4b90feef318d…"         # the claim's identity (v2.1)
sign_root    = "2fb3e5d34010…"         # the signature-chain node
build_digest = "971830be1514…"         # the concrete bytes a signature binds
fresh        = true
audit        = true
gates        = 1
components   = 0

$ ret sign conformance/kernel --check                # what a verifier sees today
authorized = false                     # nothing has been authorized yet
```

Note the two different hashes. The **root** names the claim — an equivalence
class of implementations. The **build digest** names the concrete bytes
present now. A signature binds both: it says *this person vouches for this
claim, as realized by these exact bytes.* That is why authorization freezes
an implementation even though identity floats above it.

## Step 0 — the trust anchor (a decision, not a formality)

There is currently no `~/.config/reticuli/allowed_signers` and
`RETICULI_SIGNERS` is unset. Trust here is **verifier-relative**: with no
anchor, nothing is authorized *to you*, even your own signature. The anchor
names the identities you are willing to treat as authoritative, so writing it
is a trust decision that belongs to you alone.

```
mkdir -p ~/.config/reticuli
printf '%s %s\n' 'you@lab' "$(cat ~/.ssh/id_ed25519.pub)" \
  >> ~/.config/reticuli/allowed_signers
```

Use whatever identity string you want verifiers to see; it is the name your
signature carries.

## Step 1 — authorize

```
cd /path/to/reticuli
ret sign conformance/kernel --key ~/.ssh/id_ed25519 --as you@lab
```

## Step 2 — verify what you just did

```
ret sign conformance/kernel --check
# expect: authorized = true, and a row naming your identity with
#         chain_holds / packet_holds / proof_recorded

ret status conformance/kernel          # phase should now read: signed
```

The phase moves `sealed → signed` only when authorization AND a recorded
proof are both present and the signature verifies against an anchor you
trust. A signature from an untrusted key, or a proof with no signature,
leaves the claim `sealed`.

## What a signature here asserts — and what it does not

**Asserts:** you vouch that this claim, realized by these exact bytes, is
what it says it is, on the evidence recorded beside it.

**Does not assert:** that the two rebuilds were independent. They were
produced by different vendors, which is evidence, not proof — both models may
share training data, and confinement in each rebuild was instructed rather
than jailed. The crosscheck says so in its own words
(`independence: unestablished`), and signing does not upgrade that.

**Does not assert:** that every conforming kernel agrees this claim holds.
Three independent kernels were asked to judge the v2.1 crosscheck and one
dissented — a defect in its `audit`, confirmed by hand-auditing the machines
without any judge, but a dissent nonetheless
(`crosscheck-v21-2026-09-15.md`). What you would be vouching for is the
claim on the recorded evidence, not a unanimous verdict.

## Also prepared: the lineage links

`v1-link.md` states which v1 claim each v2 claim descends from, with the
evidence graded — quirkcalc's pairing is verifiable by hashing files, the
kernel's rests on a recorded AST-identity audit. Those pairs are worth
attesting in the same sitting, and `ret attest` is the verb for vouching
without authorizing:

```
ret attest examples/quirkcalc --key ~/.ssh/id_ed25519 --as you@lab
```

## If you would rather not sign yet

Nothing downstream is blocked. A `sealed` claim with a recorded proof is a
complete, checkable artifact; signing adds a person's name to it. The claim
does not decay while it waits.
