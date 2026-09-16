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

## What the tool says, and how to read it

```
$ ret assess examples/weak --mutants 26
  circularity  ok        the gate is decided by pinned files, not generated code
  mutation     0.77      20 of 26 injected faults detected; sampled 26 of 26 sites (100%)
               1.00      branch: 4 of 4 detected, 4 sites
               0.80      comparison: 8 of 10 detected, 10 sites
               0.33      constant: 2 of 6 detected, 6 sites
               1.00      return: 3 of 3 detected, 3 sites
               1.00      string: 3 of 3 detected, 3 sites
               survivor  classify.py:7:13:comparison:<-><=
               survivor  classify.py:7:15:constant:10->10+1
               survivor  classify.py:7:15:constant:10->10-1
```

Read that carefully, because it is the most useful lesson in this repository.

**Circularity passes.** The test is a pinned file, not generated code, so the
oracle is not the artifact. That check is doing its job and it is not enough.

**The aggregate rate is nearly useless here, and the breakdown is not.** A bare
0.77 reads as a fairly well-tested claim. The per-kind rates say something
quite different: branches, returns and string results are pinned perfectly,
and **constants score 0.33**. Every one of the six survivors is a threshold
moved by one, or a `<` that became `<=` — which is to say, the entire blind
spot sits at the boundaries, which is exactly where the 10/100 and 40/200
implementations differ. The number that matters was averaged away.

This example is also why the injector reports its own fault model. An earlier
version could only swap operators, and scored this claim **0.80 while being
structurally incapable of mutating a constant** — the one fault class that
mattered. Widening it moved the aggregate by 0.03, because the added operators
brought easy kills along with the hard survivors. **Widening a fault model
does not fix an aggregate; reporting the model is what fixes it.**

The moral is not that mutation testing is bad. It is that **no single rung is
sufficient**, which is why the assessment is a ladder:

| rung | would it catch this? |
|---|---|
| circularity | no — the test is genuinely independent of the code |
| mutation | yes, but only if you read the breakdown — `constant: 0.33` is the finding, `0.77` is not |
| re-derivation | likely — an independent model reconstructing from three points would pick its own thresholds, and land somewhere else |
| generalization (held-out) | yes — hide a case, and the rebuilt implementation cannot recover it from the rest |

## How to fix a claim like this

Not by editing the implementation. By **naming the behaviour in the tests** —
values at 9, 10, 99, 100, and a statement about what happens between them.
Then the claim's root changes, because the claim changed: you are now
demanding more, and a different set of programs satisfies it.

That is the whole workflow this repository is for. Passing tests is not the
evidence. What the tests *exclude* is the evidence, and it can be measured.
