# The same loop on software nobody here wrote

*An external target, preregistered before any room opened. The working
record is [`research/external/jq/`](../research/external/jq/); the
preregistration and its falsifiable predictions are
[`preregistration.md`](../research/external/jq/preregistration.md).*

Applying the loop to reticuli's own boundary risks measuring the author.
jq is the control: a widely deployed tool with an official test suite, three
independent human implementations, and no connection to this project.

The frozen jq 1.8.1 corpus became the starting specification. Reference jq,
gojq and jaq stay permanently outside it — they adjudicate, and are never
criteria.

## Four findings, including the ones that went against the hypothesis

### The premise, free

jq, gojq and jaq disagree on **149 of 522** cases in jq's own official test
corpus, which is 28.5%. All three return the same verdict on 373: 332 passed
by all three, 41 failed identically by all three.

An official boundary is measurably incomplete before any model is involved.

### A corpus is not a criterion

The first blind rebuild converged on the first attempt: 465 of 465 on the
evaluation-core slice, root equality, `ret verify` clean. A formal member of
the class.

Differential probes over 1,395 seeded-random inputs the corpus never shows
then returned the shape that tells the story. The sample agreed with
reference jq on 587 probes and errored on 808 — every divergence the same
kind. Its own docstring explained why: *"The supplied specification is an
extensional set of observations… This is not a general jq interpreter."* It
was a 465-entry lookup table with careful input normalization and an error
for everything else.

Finite observations admit their own memorization. The repair was laws checked
against inputs generated fresh at gate time, which cannot be precomputed, and
the next rebuild was a real interpreter.

Worth being precise about the limit: generated-input obligations do not
categorically exclude table-based strategies. They make memorizing the fixed
corpus insufficient and force any table to cover the generator's reachable
input space. An implementation that memorized the *generator* would still
defeat them.

### A signed repair contracted the specification's silence — after the first
measurement of it was refuted

Generation 3 reported that divergence contracted 25% after one signed repair,
from a mean of 65.7 to 49.5 per sample.

A preregistered control at an **unchanged** boundary refuted it within the
hour. Three fresh samples at the same boundary scored 74, 68 and 47, a mean
of 63.0 — statistically indistinguishable from the 65.7 before the repair,
and *higher* than the 49.5 that had been claimed. The within-boundary spread
was larger than the effect. The aggregate claim was withdrawn.

What survived is the paired per-behavior analysis, which is where the
information actually lives: **15 behaviors closed and 1 opened** (exact
binomial *p* = 0.00026), with the closed ones traceable by name to the laws
that closed them. The aggregate count discards the pairing.

That analysis was specified *after* the aggregate analysis failed, which is
an adaptive-analysis threat and is disclosed as one. The fix is to run it on
a boundary pair it has never seen.

### Repairs are class-specific, and visible contraction is family-specific

The same repair produced no contraction at all for the other model family:
34 before, 34 after, 12 closed and 12 opened, perfectly symmetric churn, sign
test *p* = 0.58.

The class decomposition explains it. The repair targeted over-permissiveness,
which is 54% of one family's divergence and 18% of the other's. It closed
that class in both families and moved only one family's total.

Whether a specification improved cannot be read off one aggregate score. The
claude leg is n = 1 per boundary and carries no statistical weight on its
own; its value is that the decomposition explains the discrepancy and makes a
falsifiable prediction.

## The limits, stated as plainly as the findings

Sampled reconstruction finds a concentrated, high-value **fifth** of the
divergence surface the human implementations expose: recall 60 of 340 =
17.6% against a preregistered 30%. That prediction is **falsified**.
Enrichment over the base rate is 2.30×, and the concentration ratio is 60 of
107 = 56.1%.

Adding a second model family moved recall by 2.6 points. No genuinely novel
ambiguity was sample-found.

No baseline was run. A reviewer will reasonably ask whether ordinary
differential testing against gojq and jaq would have found the same
divergences more cheaply, and the honest answer is probably yes for the
divergences and no for the lookup table, since a memorization failure is only
visible when you *generate* an implementation.

## Found in passing

The probes turned up three undocumented divergences in deployed software, two
of them in reference jq, each reproducible in one command:
[`ecosystem-findings.md`](../research/external/jq/ecosystem-findings.md).
