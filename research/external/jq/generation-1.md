# jq generation 1 — the extensional collapse

*2026-10-11. Sample 1, codex, blind room at root d275f7f162c9. The
sample is DESTROYED per design commitment 5; its one file is kept as
the seam's witness (evidence/sample1-the-lookup-table.py).*

## What happened

The blind rebuild converged first attempt: 465/465 on S_0, root
equality, `ret verify` clean — a formal member of the class. The
differential probes (1,395 seeded-random inputs the corpus never
shows; probe_differential.py) then returned the shape that tells the
whole story: the sample AGREES with reference jq on 587 probes and
ERRORS on 808 — every single divergence the same kind. The source
confirms why, in the sample's own words: "The supplied specification is
an extensional set of observations. These observations are represented
explicitly... This is not a general jq interpreter." It is a 465-entry
lookup table with careful input normalization (object order ignored,
number tokens preserved, BOM handled, jq's nonstandard nan literals
accommodated) and an error for everything else.

## The finding

**The criterion admits its own memorization.** S_0 is finite and
extensional; the cheapest member of the class it defines is a table of
the observations, and a rational producer built exactly that — and
documented it, honestly. This is not a jq-semantics seam and it is not
in H (gojq and jaq are real evaluators); it is a seam in the BOUNDARY'S
FORM, and the deepest lesson of the arm so far:

    A corpus is not a criterion. A finite set of observations cannot
    specify an intensional object (a function over an infinite domain),
    and any domestication that seals a wild test suite as-is will admit
    the lookup table as its first citizen.

The reticuli self-claim never met this seam because its criteria are
PROGRAMS — checks that compute properties and probe behavior
parametrically — not observation tables. The wild world's barriers are
extensional almost everywhere. Domestication's first repair is forcing
intension.

## The staged repair (S_0 → S_1), for the keyholder's signature

Add PROPERTY CRITERIA to the gate — metamorphic laws that need no
oracle and hold over GENERATED inputs (seeded inside the gate, fresh
shapes every audit):

    .a on {"a": X}        == X                 (indexing law)
    (A | B) on X          == B on (A on X)     (composition, sampled)
    sort | sort           == sort              (idempotence)
    length on (a + b)     == length a + length b   (for arrays/strings)
    fromjson | tojson roundtrips on generated values
    ... (a dozen such, drawn from the manual's own algebraic claims)

A lookup table cannot pass laws over inputs that do not exist until the
gate runs; a real evaluator passes them for free. The oracles stay
outside S (commitment 4 holds: the laws come from jq's documented
algebra, adjudicated by the manual, not by running jq inside the gate).
S_1 = S_0 + the law battery; a signed root move on the jq claim; then
generation 2 sampling begins.

## Scored against the preregistration

- P4 held and then some: conformance itself — not just convergence — is
  uninformative when the boundary is finite. The probes detected it
  immediately; the instrument works.
- P1–P3 are NOT YET SCORED: M is dominated by the table's refusals, not
  semantic divergence; scoring recall/novelty waits for generation 2,
  when samples are forced to be evaluators.
- Independent yield, banked: on the SAME probe set, the HUMAN
  implementations split from reference jq on 296 of 1,395 novel probes
  — live divergence territory outside the corpus, harvested for the
  recall denominator (probes_g1_sample1.json).
