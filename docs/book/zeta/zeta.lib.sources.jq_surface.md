# `zeta/lib/sources/jq_surface.py`

**Pressure on the jq language, put to three independent implementations.**

A foreign population matters for one specific reason. In the reticuli
population the criteria and the candidates share an author lineage, so a tight
class may be tight partly because of that. The jq language was specified by
somebody else and implemented three times by people who were not coordinating,
which makes it the control: a criterion that keeps admitting strangers cannot
have been overfitted to us.

The probes below are grouped by the kind of silence they test, and every one
names what it is asking. They concentrate on the places a language
specification usually stops short -- what happens on error, how numbers are
printed, whether ordering is promised, what a path expression does to a
missing key -- because that is where three good-faith implementations diverge
without any of them being wrong.

`-c` is passed to every member so output framing cannot masquerade as a
semantic difference.

```python
from __future__ import annotations
```

(name, program, input document, what is being asked)

```python
CASES = [
```

Arithmetic and number printing: where a language says "number" and
leaves the representation to the implementation.

```python
    ("large-integer", ".", "100000000000000000000",
     "is an integer beyond double precision preserved or rounded"),
    ("integer-float-identity", ". == 1", "1.0",
     "is 1.0 the same number as 1"),
    ("division-exact", "1/3", "null",
     "how many digits does a non-terminating quotient print"),
    ("negative-zero", "-0", "null", "is negative zero distinguished"),
    ("big-exponent", ".", "1e1000", "what becomes of an overflowing literal"),
```

Errors: the most under-specified region of any language.

```python
    ("divide-by-zero", "1/0", "null", "which error, and on which exit code"),
    ("index-a-number", ".foo", "3", "indexing a non-object"),
    ("add-mismatched", '1 + "a"', "null", "adding a number to a string"),
    ("error-no-message", "error", "null", "error with no argument"),
    ("error-object", 'error({"a":1})', "null", "error carrying a non-string"),
    ("tostring-of-error", "try error(1) catch .", "null",
     "what a caught non-string error becomes"),
```

Object semantics: ordering and duplicate keys, rarely promised.

```python
    ("key-order", ".", '{"b":1,"a":2}',
     "is object key order preserved or normalised"),
    ("duplicate-keys", ".", '{"a":1,"a":2}', "which duplicate key survives"),
    ("keys-unsorted", "keys_unsorted", '{"b":1,"a":2}',
     "does keys_unsorted mean insertion order"),
```

Paths and absence: the difference between absent and null.

```python
    ("missing-key", ".nope", "{}", "a missing key against an explicit null"),
    ("nested-missing", ".a.b.c", "{}", "a missing path several levels down"),
    ("path-of-missing", "path(.a[0].b)", "{}",
     "can a path be taken through absence"),
    ("delete-missing", "del(.nope)", '{"a":1}', "deleting what is not there"),
```

Strings and unicode: encoding decisions a spec often leaves open.

```python
    ("lone-surrogate", ".", '"\\ud800"', "an unpaired surrogate in a literal"),
    ("combining-mark", "length", '"e\\u0301"',
     "is length counted in code points or graphemes"),
    ("implode-invalid", "[55296] | implode", "null",
     "imploding a surrogate code point"),
    ("ltrimstr-nonstring", "ltrimstr(1)", '"abc"',
     "a string function given a non-string"),
```

Sorting and comparison across types, where a total order must be chosen.

```python
    ("sort-mixed-types", "sort", '[null,true,1,"a",[],{}]',
     "the cross-type total order"),
    ("sort-objects", "sort", '[{"b":1},{"a":1}]', "how objects compare"),
    ("unique-nan", "unique | length", "[0,-0]",
     "do positive and negative zero coincide"),
```

Limits: recursion and size, always implementation-defined.

```python
    ("deep-recursion", "[limit(3; repeat(.))]", "1",
     "is repeat with limit lazy"),
    ("tostream-roundtrip", "[tostream] | length", '{"a":{"b":1}}',
     "the shape of a stream decomposition"),
]


def pressures():
    for index, (name, program, document, asking) in enumerate(CASES):
        yield {"schema": "zeta.pressure.1",
               "source": "jq_surface",
               "id": f"jq/{name}",
               "clause": name,
               "simplicity": index,
               "call": "run",
               "args": [program, document],
               "specified_reader_behaviour": asking,
               "origin": "the jq language as documented; see "
                         "research/external/jq/corpus"}
```

---
*Generated from `zeta/lib/sources/jq_surface.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
