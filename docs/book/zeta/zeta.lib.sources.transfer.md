# `zeta/lib/sources/transfer.py`

**Silences carried across from a foreign population, by shape and not content.**

Every other source here derives its pressure from this system: probes read out
of the specification, mutants made by perturbing the implementation. Both can
only drive the specification toward being a fixpoint of itself. If reticuli has
no notion of some thing, nothing inside reticuli will propose one -- which is
why four rounds of pressure produced only tightenings of what was already
written down.

This source looks somewhere else. The jq population is three independent
implementations of a language specified by people who never heard of this
project, and its disagreements expose the PLACES a specification of that kind
tends to stop short. Those places transfer; the content does not. A split about
`keys_unsorted` says nothing about reticuli, but the shape of it -- *a
specification that names a vocabulary without saying whether every member of
it must exist* -- is a question one can put to any specification.

So each pressure below names the foreign silence it carries, and `transfers`
records both halves: which population exposed it, and in what. That provenance
is what lets a finding claim the fourth rung, and the reason it is required is
that no system can assert novelty about its own vocabulary. The claim is only
ever as good as the silence it came from.

THE FIRST TRANSFER ALREADY PAID. jq's number-representation splits
(`integer-float-identity`, `division-exact`, `big-exponent`) prompted asking
whether the record format had a position on numeric form. It did not; the
clause that resulted was signed on 2026-10-14, and the same question asked one
layer deeper produced the finite-cost counterexample that moved the root. None
of the other sources could have reached either, because the specification
contained nothing to probe and the implementation nothing to mutate.

```python
from __future__ import annotations

HEX = "a" * 64

BASE = {
    "record": 2, "claim": {}, "name": "example", "root": HEX,
    "build_digest": HEX,
    "gates": [{"output": "EXAMPLE_OK", "status": "ok", "sandbox": "seatbelt"}],
    "environment": {"platform": "darwin", "machine": "arm64", "runtime": "3.14"},
    "when": "2026-10-14T00:00:00Z",
}
```

(name, the foreign silence, the jq witnesses, call, document, what is asked)

A transfer is only as good as its provenance, so `witnesses` names the jq
probes that exposed the shape. They are in zeta's own queue, at third kind.

```python
CASES = [
    ("lone-surrogate-in-a-string",
     "whether a text field admits a code point that is not a character",
     ["jq/lone-surrogate"],
     "record_validate", dict(BASE, name="\ud800"),
     "jq refuses to parse an unpaired surrogate and gojq substitutes U+FFFD; "
     "the record format says `name` is a non-empty string and nothing about "
     "what a string may contain, so two readers may disagree about a document "
     "that is valid JSON by one parser and not by another"),

    ("lone-surrogate-in-an-environment-field",
     "whether the same silence reaches every text field or only the named one",
     ["jq/lone-surrogate"],
     "record_validate",
     dict(BASE, environment={"platform": "\udfff", "machine": "arm64",
                             "runtime": "3.14"}),
     "the same question one level down: a field the spec describes only as a "
     "string, where a per-field answer would mean the format has no rule"),

    ("float-where-an-integer-is-specified",
     "whether a declared integer admits a float of equal value",
     ["jq/integer-float-identity"],
     "record_validate", dict(BASE, record=2.0),
     "jq's splits show implementations disagreeing about whether 1 and 1.0 are "
     "one number; the record format calls `record` an integer, and 2.0 is "
     "equal to 2 while not being an int, so a reader may admit or refuse it"),

    ("float-where-a-version-is-counted",
     "whether an out-of-range float is caught by range or by type",
     ["jq/integer-float-identity", "jq/big-exponent"],
     "record_validate", dict(BASE, record=2.5),
     "a non-integral float at the same position: a reader checking only the "
     "value's range would admit 2.0 and refuse 2.5, while one checking type "
     "refuses both, and the difference is invisible until someone sends 2.0"),

    ("fractional-count-where-calls-are-counted",
     "whether a count admits a non-integral number",
     ["jq/agent-jq-paths-00"],
     "record_validate", dict(BASE, cost={"calls": 1.5}),
     "the agentic pilot's fractional-index split, carried by shape: asked for "
     "path(.[1.7]), jq and gojq construct the path and jaq refuses to index "
     "with a fraction -- two defensible readings of a number standing where "
     "something countable is meant. The record format types every cost value "
     "only as a finite non-negative number, and `calls` is a count of API "
     "round trips, so a reader may admit half a call or refuse it; nothing "
     "written decides"),

    ("negative-zero-where-negative-is-refused",
     "whether the sign of zero is a value or a representation",
     ["jq/integer-float-identity", "jq/agent-jq-paths-00"],
     "record_validate", dict(BASE, cost={"usd": -0.0}),
     "the same family of number-identity splits, at the boundary the spec "
     "draws: a cost must be non-negative, and -0.0 is not less than zero, so "
     "a reader checking `value < 0` admits it while one checking the sign "
     "bit refuses -- and the admitted document then canonicalises a number "
     "whose textual form may or may not keep the sign"),

    ("digest-of-a-surrogate-bearing-record",
     "whether an unencodable character survives canonicalisation",
     ["jq/lone-surrogate", "jq/implode-invalid"],
     "record_digest", dict(BASE, name="\ud800"),
     "if a reader admits a lone surrogate, the canonicaliser must still turn "
     "it into bytes to be cited; jq's implode split is the same question, "
     "and a digest that cannot be computed is a record that cannot be named"),
]

SURFACES_NOTE = ("Each case targets one kernel call directly, because the "
                 "silences being carried are about what a document may "
                 "contain rather than about which entry point reads it.")


def pressures():
    for index, (name, silence, witnesses, call, document, asking) in enumerate(CASES):
        yield {"schema": "zeta.pressure.1",
               "source": "transfer",
               "id": f"transfer/{name}",
               "clause": name,
               "simplicity": index,
               "call": call,
               "args": [document],
               "specified_reader_behaviour": asking,
               "origin": "a silence carried from the jq population",
```

Both halves are required, and a finding without them cannot
reach the fourth rung: novelty about one's own vocabulary is
not a thing a system gets to assert.

```python
               "transfers": {"from": "jq", "silence": silence,
                             "witnesses": witnesses}}
```

---
*Generated from `zeta/lib/sources/transfer.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
