# The reference corpus

*Research record — how assess evidence accumulates. Not normative; the corpus is
residue and never a root input.*

`ret assess` measures how much a claim's tests constrain its code. Some of what
it reports is meaningful the moment it is computed — circularity, a mutation
rate. But its deepest rungs are comparisons: *blind re-derivation succeeded*,
*two producers converged*, *this mutation rate is high* mean little against a
sample of one. They gain resolution only as a body of runs accumulates. The
corpus is that body.

## What it is

An append-only file of flattened assess results — one JSON record per run,
carrying the measured numbers and when they were taken, nothing tied to one
machine's presentation. `ret assess --corpus <file>` reads the existing
population, reports where this claim sits in it, and then adds this run:

```
$ ret assess myclaim --corpus research/corpus/assess.jsonl -v
  ...
  against the corpus
  population     14 prior run(s) in the corpus
  mutation       rate 0.60 vs median 0.72 across 11 (37th percentile)
  blind re-derivation   this failed; population 0.64 of 14
```

A claim is always placed against the population *before* this run, so it is
never compared against itself.

## The one hard rule

The corpus **calibrates how a claim is read, never what it is.** It is residue,
outside every root; capturing more of it, or capturing it badly, can never move
an identity. The single doorway by which the population legitimately reaches
identity — deciding to pin a `mutation_floor` or a cost envelope informed by
what the corpus shows is achievable — stays a keyholder's deliberate authoring
act, made through the transition ritual, never something a measurement does on
its own. Evidence advises; the human pins.

This is the same separation the whole tool rests on: the trace has zero
authority and the cold re-earn seals; here, the population has zero authority
and the pinned criteria decide.

## Tracking it

Whether a corpus file is committed is a choice for whoever keeps it, not the
tool's: it is not a root input either way. A shared, committed corpus becomes a
project's accumulated reference population; a local, gitignored one is a single
operator's working sample. `ret assess --corpus` appends to whatever file you
name. Reticuli's own research runs accumulate here, in
`research/corpus/assess.jsonl`.
