# Refuse a broken composed audit at its layer, not at assembly

2026-10-15. Staged for a keyholder signature. A **contraction**: the authored
tree passes as written and no current member is evicted. Not landed here.

There is nothing to fix in the implementation. The authored `audit_deep` is
correct — 18 layers for 18, keeping `kernel.audit`'s shape. What is wrong is
*where* the obligation is checked.

## The measurement

The r26 claude reconstruction has a genuinely broken `audit_deep`: it reports
311 layers where 18 are correct, and it omits the top claim's own gates from
the composed verdict. Put each criterion to that tree directly:

```
surface_check.py   PASSES
self_check.py      refuses -- "every chained layer beneath surface is judged"
```

`surface_check.py` is the layer-local criterion that judges `registry.py`. It
accepted the defect. The producer therefore got no signal at layer 18, grew
three more layers, and learned of the refusal at assembly — four hours in,
with the cause two removes from the code that caused it.

And the coverage is not absent, only weak. A mutant of the AUTHORED tree that
drops `top = kernel.audit(...)` is killed by `surface_check` as well as
`self_check`, in fifty seconds. So surface_check does test the shape; it does
not test the walk, and claude's tree fails the walk.

## Why the layer cannot currently catch it

`self_check` builds the whole nineteen-layer chain and counts. A layer check
has no chain to walk, so it tests `audit_deep` against whatever fixture it
carries — and on a one- or two-deep fixture a non-memoising walk and a correct
one give the same answer. The duplication only becomes visible with depth.

## The proposed criterion

Give `surface_check.py` a **three-layer fixture chain** and assert, against
it, exactly what `self_check` asserts against the real one:

```python
# A three-deep chain is the smallest fixture where a walk that forgets what it
# has audited diverges from one that does not: a correct audit_deep reports
# two components beneath the top, a non-memoising one reports more.
deep = registry.audit_deep(fixture_top)
assert deep["ok"], deep.get("verdict")
assert len(deep["layers"]) == 2, \
    f"each component beneath the top is judged exactly once, got {len(deep['layers'])}"
assert [l["name"] for l in deep["layers"]] == sorted({l["name"] for l in deep["layers"]}), \
    "a component judged twice is a walk that does not remember"
assert "root" in deep and "gates" in deep, \
    "a composed verdict keeps kernel.audit's shape: the claim's OWN gates compose too"
```

Three layers is the minimum that discriminates. With two, a forgetful walk and
a correct one agree; with three, the forgetful one revisits the bottom layer
through two paths.

## What it costs and does not cost

The authored tree passes every line of it today, so this is a contraction that
evicts nobody. It moves the root, and it will retire the reconstruction
population — currently `shipped` and `r25-codex` — which argues for batching it
with the other staged item from today, the uncanonicalised build digest, so
one signature costs one rebuild.

It does not change `self_check`. The assembly-level check stays as the
backstop; this adds the fast signal in front of it.

## Fix the assertion's words while in there

`self_check.py` line 532 reads "every chained layer beneath surface is
judged". What it enforces is each layer judged *exactly once* — claude's tree
judges every one of them, 311 times. A message that under-describes its own
assertion cost real time when the refusal was being diagnosed.

## What this is the third of

An obligation placed where it cannot steer:

1. The cost boolean guard and the closed band, written into a repo-level check
   when both are single-function properties of `run.py`. Recorded during r25.
2. The finite-cost reader assertion, placed in the same repo-level check the
   same day, for the same reason, after recording the lesson.
3. This one — and the first with a measured witness, since claude's tree shows
   what the delay costs: four hours and a diagnosis two removes from the code.

The pattern is worth naming: a criterion that catches everything at assembly
is sound and nearly useless as feedback. Where an obligation is local to a
layer, it belongs in that layer's check, and the assembly check should be the
backstop rather than the only net.
