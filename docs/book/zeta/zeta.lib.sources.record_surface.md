# `zeta/lib/sources/record_surface.py`

**Pressure derived from the record specification's own validation sentence.**

`spec/record.md` has a Validation section naming, in one sentence, every
document a reader must refuse: not an object, a version newer than understood,
a missing required member, a member the spec does not name at that version, a
`root` or `build_digest` that is not 64 lowercase hex characters, a `status` or
`sandbox` outside the vocabularies, a cost value that is boolean or negative,
and a `claim` with an unknown key, a negative floor, or a bad envelope.

That sentence is a probe family. Each clause names an input class, and the
kernel exposes three functions that consume documents, so every clause can be
put to every member. Reading pressure out of the specification rather than
mutating strings means each finding points at a sentence someone already
wrote, which is what makes a queue entry cheap to sign.

ATTRIBUTABILITY IS THE WHOLE DESIGN CONSTRAINT. Every case below is the one
well-formed base document with exactly one clause violated. A base that is
itself invalid makes every case refuse for the wrong reason, and the family
silently stops testing what it claims to test -- which is how the first
version of this file was wrong: its base omitted three required members, so
all nineteen documents were invalid and no clause was attributable.

The spec assigns refusal to "a reader" and names `record_read` as the reader.
It does not say whether the canonicalizer validates. That silence is not a gap
in this source; it is the kind of thing this source exists to surface.

```python
from __future__ import annotations

HEX = "a" * 64
```

Required at version 2, per the member table: record, claim, name, root,
build_digest, gates, environment, when. Optional: cost, producer, tool.

```python
BASE = {
    "record": 2,
    "claim": {},
    "name": "example",
    "root": HEX,
    "build_digest": HEX,
    "gates": [{"output": "EXAMPLE_OK", "status": "ok", "sandbox": "seatbelt"}],
    "environment": {"platform": "darwin", "machine": "arm64", "runtime": "3.14"},
    "when": "2026-10-14T00:00:00Z",
}


def _without(member):
    doc = {k: v for k, v in BASE.items() if k != member}
    return doc


def _with(**overrides):
    return {**BASE, **overrides}


def _gate(**overrides):
    return _with(gates=[{**BASE["gates"][0], **overrides}])
```

Each case names the clause it exercises. `specified_reader_behaviour` records
what the spec says a READER does; it is never used to decide a lane, because
the lane is decided by what members actually do.

```python
CASES = [
    ("well-formed-v2", BASE,
     "accepted: every required member present, no member the spec does not name"),
    ("well-formed-v1", {k: v for k, v in BASE.items() if k != "claim"} | {"record": 1},
     "accepted: claim must be absent at version 1"),
    ("not-an-object", ["not", "an", "object"],
     "refused: document is not a JSON object"),
    ("missing-record", _without("record"), "refused: missing required member"),
    ("missing-name", _without("name"), "refused: missing required member"),
    ("missing-gates", _without("gates"), "refused: missing required member"),
    ("missing-environment", _without("environment"), "refused: missing required member"),
    ("missing-when", _without("when"), "refused: missing required member"),
    ("unknown-future-version", _with(record=99),
     "refused: version newer than understood, naming the version"),
    ("unnamed-member", _with(surprise="x"),
     "refused: member the spec does not name at this version"),
    ("claim-at-version-1", _with(record=1),
     "refused: claim must not appear at version 1"),
    ("claim-missing-at-version-2", _without("claim"),
     "refused: claim is required at version 2"),
    ("root-not-hex", _with(root="z" * 64), "refused: root is not hex"),
    ("root-uppercase", _with(root="A" * 64), "refused: root is not LOWERCASE hex"),
    ("root-short", _with(root="a" * 63), "refused: root is not 64 characters"),
    ("build-digest-not-hex", _with(build_digest="z" * 64),
     "refused: build_digest is not hex"),
    ("status-outside-vocabulary", _gate(status="probably"),
     "refused: gate status outside the audit vocabulary"),
    ("sandbox-outside-vocabulary", _gate(sandbox="maybe"),
     "refused: gate sandbox outside the confinement vocabulary"),
    ("cost-boolean", _with(cost={"usd": True}),
     "refused: a cost value is never a boolean"),
    ("cost-negative", _with(cost={"usd": -1}),
     "refused: a cost value is non-negative"),
    ("cost-unknown-key", _with(cost={"grue": 1}),
     "refused: cost holds a subset of exactly four keys"),
    ("claim-unknown-key", _with(claim={"nonsense": 1}),
     "refused: claim key outside the three obligations"),
    ("claim-floor-negative", _with(claim={"mutation_floor": -1}),
     "refused: mutation floor is negative"),
    ("claim-envelope-empty", _with(claim={"envelope": {}}),
     "refused: envelope is empty"),
    ("claim-envelope-unknown-unit", _with(claim={"envelope": {"grue": 1}}),
     "refused: envelope unit outside the cost vocabulary"),
    ("claim-envelope-zero", _with(claim={"envelope": {"usd": 0}}),
     "refused: envelope ceiling is not a positive number"),
]

SURFACES = ["record_validate", "record_canonical", "record_digest"]


def pressures():
    """Every clause against every document-consuming surface."""
    for call in SURFACES:
        for index, (name, document, expectation) in enumerate(CASES):
            yield {"schema": "zeta.pressure.1",
                   "source": "record_surface",
                   "id": f"{call}/{name}",
                   "clause": name,
```

Simplicity order within a surface, used to pick the
minimal witness when many clauses induce one phenomenon.

```python
                   "simplicity": index,
                   "call": call,
                   "args": [document],
                   "specified_reader_behaviour": expectation,
                   "origin": "spec/record.md, Validation"}
```

---
*Generated from `zeta/lib/sources/record_surface.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
