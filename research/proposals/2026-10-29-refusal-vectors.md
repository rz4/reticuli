# A conformance vector may pin a refusal, not only a value

2026-10-29. Staged for a keyholder signature. A **contraction**: it closes
coverage the current vector set cannot express. It would move the root (new
pinned vector files plus a changed `vectors_check.py`), and it is **not
landed here** — what landed today is only the honest statement of the gap in
`spec/vectors/README.md`.

## The measurement

`spec/vectors/` now holds 21 directories, every one of them a **positive
root**: a well-formed claim and the hex its root must equal (plus a build
digest where one is pinned). `criteria/vectors_check.py` requires the
kernel, the reference, and the pinned value to agree, and has teeth — a
tampered vector must fail and be named.

What no vector exercises is the other half of `spec/identity.md`: the
**refusal surface**. Specified, implemented, and uncovered —

| rule (`spec/identity.md`, *File hashing rules*) | covered? |
|---|---|
| a declared path that is absolute | no |
| a declared path that is empty | no |
| a declared path containing a `..` component | no |
| a declared path with a **symlink component, even one staying inside the claim** | no |
| a hashed file that is a FIFO, device, socket, or directory | no |
| a hashed file with `st_nlink > 1` (a hardlink to an outside inode) | no |
| a TOML date or time value anywhere in a recipe (`spec/identity.md`, canonicalization) | no |

So the published conformance claim was, until today's correction, "an
implementation conforms **exactly when** it reproduces every expected
value" — and an implementation can satisfy that at 21/21 while *sealing*
claims this specification says must be refused.

**That is the more dangerous direction.** A wrong root is self-announcing:
the next crosscheck fails and someone investigates. A wrongly-admitted claim
is silent — it gets a name, travels, and is signed. The symlink rule is the
sharpest case, and this repository already paid for it once: before
2026-09-16 the two shipped implementations *disagreed* about internal
symlinks, one sealing and one refusing, so whether a claim existed depended
on which kernel looked at it. That is exactly the class of divergence the
vectors exist to prevent in foreign implementations, and it is the class
they do not test.

## Why it cannot be expressed today

A vector is a directory plus `expected-root`. A refusal has no root, so the
format has nothing to compare. `vectors_check.py` discovers vectors by the
presence of `expected-root` (`criteria/vectors_check.py`, `battery()`), and
`spec/vectors/run.py` does the same, so a directory without one is simply
invisible to both.

## The proposal

Add a second vector kind, discovered by a second marker file:

```
spec/vectors/x1-symlink-component/
    claim.toml
    …                       the claim's files
    expected-refusal        one line: a stable REASON CODE
```

- A vector carrying `expected-refusal` must make a conforming implementation
  **refuse**. The runner asserts a refusal happened; it does not compare
  prose, because refusal *messages* are explicitly implementation-defined
  (`spec/verification.md`'s implementation-defined list) and pinning English
  would narrow the equivalence class for no gain.
- A **reason code** is what gets pinned: a short stable token
  (`path-absolute`, `path-dotdot`, `path-symlink`, `not-regular-file`,
  `multiply-linked`, `toml-datetime`). This is the one real design cost —
  the kernel does not currently emit codes, only sentences, so adopting this
  adds a code to `ClaimError` at the refusal sites named above. A cheaper
  variant pins only *that* it refused; it is weaker, because an
  implementation that refuses everything would pass.
- `expected-root` and `expected-refusal` are mutually exclusive; a vector
  carrying both is itself a malformed vector and the check says so.
- One rule per vector. The v12 pair is the cautionary case in the existing
  set: it varies step order *and* guidance presence at once, so a failure
  cannot be attributed, against the stated virtue that each vector "fails a
  specific vector by a specific amount."

## Packaging a symlink in a sealed vector

The one mechanical obstacle, and the reason this is a proposal rather than a
commit: a vector directory's files are **pinned inputs of this repository's
own claim**, and a symlink is precisely what `_safe` refuses to hash. A
vector that *contains* a symlink therefore cannot be pinned the ordinary
way. Two routes, neither free:

1. **Materialize at check time.** The vector pins a plain recipe plus a
   small manifest saying "make `link` a symlink to `target` before running".
   Everything pinned stays a regular file; the hostile shape is built in a
   scratch copy. Costs: the check gains a builder, and the builder is now
   part of the criterion.
2. **Pin the refusal without the artifact.** Keep the symlink case out of
   `spec/vectors/` and leave it where it already is — `kernel_check.py`
   exercises it against a built tree. Costs: foreign implementations, the
   whole point of the vector set, still cannot run it.

Route 1 is recommended. Route 2 is what exists today and is why the gap
exists.

## What this would cost, honestly

Every current member of the reconstruction population is retired when the
root moves, and the closure count resets to zero by condition 7 — which is
already 0 of 3 at the current root, so the marginal cost is lower now than
it will be later. Against that: the vector set is the *only* instrument that
reaches implementations this repository's own suite cannot, and it is
currently blind to the half of the specification where admitting a bad claim
is the failure.

Recommended as a batch with any other staged identity-bearing change, so the
population retires once.
