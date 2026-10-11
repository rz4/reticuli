# Instrument-found divergences in the wild jq population

*2026-10-11. Discoveries about the EXISTING implementations (jq 1.8.1,
gojq 0.12.19, jaq 3.1.1), found while authoring S_2's error laws — not
by a reconstruction sample. Recorded separately from the preregistered
P3 (which requires a SAMPLE-surfaced divergence) so the provenance of
each claim stays exact. Both are reproducible in one command.*

## 1. `reverse` on `0`: jq returns `[]`, gojq and jaq both error

    $ echo 0 | jq -c 'reverse'      -> []
    $ echo 0 | gojq -c 'reverse'    -> error
    $ echo 0 | jaq -c 'reverse'     -> error

Mechanism: jq defines `reverse` in terms of `length`, and `length` of a
number is its absolute value — so `0` yields `range(0;0)`, nothing is
indexed, and the result is the empty array. `5` yields `range(0;5)` and
dies on `.[4]` ("Cannot index number with number"). The same vacuity
makes `reverse` on `{}` return `[]` while `{"a":1}` errors. gojq and
jaq implement the type check directly and refuse all of it.

Status: **undocumented** (neither divergence README mentions it; jaq's
README names `reverse` only in a benchmark table), **absent from the
H-shadow** (its three `reverse` probes are a different program), and
**not sample-surfaced**. So: a genuine, novel, three-way split in the
ecosystem, found by this arm's generated-input probes, with jq as the
sole permissive implementation.

## 2. `range("a")` HANGS jaq

    $ echo null | jq -c 'range("a")'    -> error (type)
    $ echo null | gojq -c 'range("a")'  -> error (type)
    $ echo null | jaq -c 'range("a")'   -> HANGS (no output, no exit)

A liveness divergence, not just a semantic one: the other two refuse a
non-numeric range argument; jaq does not terminate. Found when the
error-law probe timed out. Worth reporting upstream.

## 3. The vacuity family (a complexity finding, not a divergence)

`transpose` refuses by the max `length` of its VALUES, so `{"k": 0}` is
vacuous (`[]`) while `{"a": 1}` errors. `min`, `unique`, and `sort`
share the pattern at different depths. Consequence for specification
work: **these builtins have no clean type-level error law** — their
refusal is value-dependent through jq's own prelude definitions.
`transpose` was therefore DROPPED from S_2's laws rather than contorted
into a half-true rule (three validation rounds against reference jq
caught each over-reach in turn; the measure-before-pin rule paid for
itself three times in one sitting).

## Why this matters to the method

All three findings came from the same source: **generated inputs over a
real boundary, validated against the reference before anything was
pinned.** No sample was needed to find them, and the pinning discipline
(validate the law against the reference, on fresh seeds, before sealing)
is exactly what prevented three false criteria from entering S_2. In
domestication terms: the instrument found undocumented behavior in a
20-year-old widely-deployed tool and in both of its major
reimplementations, in one afternoon, as a side effect of writing down
what the language refuses.
