# The build digest's canonical form has no criterion

2026-10-15. Staged for a keyholder signature. A **contraction**: both current
members already sort, so declaring it evicts nobody. Not landed here.

Found by zeta round five, which mutated the one surface nothing had ever
mutated — `identity.py`, where the root is computed. Five of six identity
operators died as expected. The sixth survived, contradicting its declared
expectation, which is the instrument reporting a gap rather than an opinion.

## The declared property

`src/reticuli/kernel.py`, on the build digest:

> A signature binds it, so authorization freezes an implementation even though
> the identity floats above it. **Its preimage is canonical too, so signatures
> travel.**

## The measurement

The operator removes `sorted()` from the build-digest preimage:

```python
preimage = json.dumps(sorted(own), sort_keys=True).encode("utf-8")
                     ^^^^^^^^^^^  removed
```

Against the `rd2-two-generated` vector, with its two produce steps written in
each order:

| | reorder the produce steps |
|---|---|
| authored | build digest **holds** — `b540ad3b…` both ways |
| mutant | build digest **moves** — `b540ad3b…` → `b17ede77…` |

And the mutant earns the full gate. So the property is declared, violable, and
untested.

## Why it matters, and it is not cosmetic

`spec/vectors/v12-format4-order-a` and `-order-b` differ only in the order of
their produce steps, and they pin the **same** expected root,
`f518ba9ed4b2…`. That is format 4 working as designed: the recipe's steps are
a set of obligations, so reordering them does not change the claim.

Those two recipes are therefore **one claim over one set of bytes**. A
conforming member that did not canonicalise the build-digest preimage would
compute a different build digest for each spelling. A signature binds the
build digest, so a signature issued by one member would fail to verify under
another. Signatures would not travel — exactly the guarantee above.

This is the r7 defect one level over. Step-order drift was witnessed moving a
root, and the preimage was canonicalised to fix it. The same canonicalisation
was written into the build digest and never given a criterion.

## Why the existing vector cannot catch it

This is the part worth reading, because the suite looks purpose-built for it.
`v12-format4-order-a` declares two generated outputs, deliberately out of
alphabetical order:

```toml
format = 4
[[step]] output = "beta.txt"   class = "generated"
[[step]] output = "alpha.txt"  class = "generated"
```

It pins an `expected-build-digest`. But **neither generated file exists in the
fixture**, and `build_digest` omits an absent generated output by design. So
`own` is empty, and the pinned digest is the digest of the empty list:

```
pinned:                    4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945
sha256(json.dumps([])):    4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945
```

Identical, verified. The vector exercises order canonicalisation for the root
and has nothing whatever to order for the build digest. A test that appears to
cover a property and provably cannot discriminate it is worse than an absent
one, because its presence is what stops anyone looking.

## The fix

Add `alpha.txt` and `beta.txt`, with **different content**, to both v12
fixtures, and re-pin both `expected-build-digest` files. The existing
`vectors_check` then kills this mutant for free: the two spellings must agree
on the build digest, and only a canonicalising implementation can make them.

Different content matters. Two files with identical bytes produce
`[[name, h], [name2, h]]` pairs that still differ by name, so identical
content would work — but differing content makes the failure louder and the
fixture's intent legible.

No implementation changes. Both current members already sort, so this is a
contraction that evicts nobody and the authored tree passes as written.

## What this round got wrong

Worth recording beside the finding. The operator I expected to survive was
`root-drops-the-input-prefix` — stripping the `input:` namespace so a file
named `recipe` or `digest` could shadow a structural key in the preimage. The
vectors killed it. The gap was on a surface I had not suspected, and the
expectation column is what surfaced it: a declared `killed` that lived.
