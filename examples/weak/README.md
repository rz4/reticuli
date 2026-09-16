# A weak claim, on purpose

Root `db888e0183ddb22801fdb9e62145447b40ca0a800cb6877a18e8b84f7ffb4be7`.

Every other example here is a good claim. This one is not, and it exists
because **you have no reason to trust a green result until you have seen the
tool produce a red one.**

A model wrote `classify.py` and, in the same breath, wrote the test that
judges it. The test passes. The claim seals. The verdict is `earned`. Nothing
is broken, and nothing much has been verified.

```python
def classify(value):
    if value < 10:   return "low"
    if value < 100:  return "medium"
    return "high"
```

```python
assert classify(5)   == "low"
assert classify(50)  == "medium"
assert classify(500) == "high"
```

Three assertions, one per branch. Reasonable-looking, and fitted: they name a
value inside each branch and never probe where the branches change.

## What the claim actually admits

Here is a different implementation that satisfies the identical claim — same
pinned test, same gate, **same root**:

```python
def classify(value):
    if value < 40:   return "low"
    if value < 200:  return "medium"
    return "high"
```

```
value  status           thresholds 10/100   thresholds 40/200
    5  pinned by a test low                 low
   50  pinned by a test medium              medium
  500  pinned by a test high                high
   30  NEVER TESTED     medium              low       <-- differ
  150  NEVER TESTED     high                medium    <-- differ
```

The equivalence class this root names contains both programs. That is not a
flaw in the identity scheme — it is the identity scheme reporting, accurately,
that the criteria do not distinguish them. **The claim is exactly as strong as
its tests, and its tests pin three points.**

## What the tool says, and what it misses

```
$ ret assess examples/weak --mutants 20
  circularity  ok    the gate is decided by pinned files, not generated code
  mutation     0.80  8 of 10 injected faults detected; sampled 10 of 10 sites
               survivor  classify.py:7:13:<-><=
               survivor  classify.py:9:13:<-><=
```

Read that carefully, because it is the most useful lesson in this repository.

**Circularity passes.** The test is a pinned file, not generated code, so the
oracle is not the artifact. That check is doing its job and it is not enough.

**Mutation scores 0.80 — and that number flatters the claim.** The two
survivors are exactly right: flipping `<` to `<=` at each threshold is
invisible to tests that never probe a boundary. But the fault injector mutates
*operators*, and the real weakness here is the *constants*. It cannot try
`10 → 40`, so the most important thing about this claim — that the thresholds
are essentially unconstrained — never appears in the score.

The moral is not that mutation testing is bad. It is that **no single rung is
sufficient**, which is why the assessment is a ladder:

| rung | would it catch this? |
|---|---|
| circularity | no — the test is genuinely independent of the code |
| mutation | partially — finds the boundary, misses the thresholds |
| re-derivation | likely — an independent model reconstructing from three points would pick its own thresholds, and land somewhere else |
| generalization (held-out) | yes — hide a case, and the rebuilt implementation cannot recover it from the rest |

## How to fix a claim like this

Not by editing the implementation. By **naming the behaviour in the tests** —
values at 9, 10, 99, 100, and a statement about what happens between them.
Then the claim's root changes, because the claim changed: you are now
demanding more, and a different set of programs satisfies it.

That is the whole workflow this repository is for. Passing tests is not the
evidence. What the tests *exclude* is the evidence, and it can be measured.
