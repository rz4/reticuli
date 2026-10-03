# Revision — the map's first two pins: pack's residual surface, and KINDS

*2026-10-03. An identity-bearing transition, keyholder-signed. The first
clicks taken directly from the layer surface-silence map — seams pinned
from a measurement, before they bit anything.*

    old root  03edfbb733adf44b1a840cbfc6a99736f2deea7fcccbc4718f96bf28e9726728
    new root  51635f095d0fdd7d04a3b0541ac5bf006c8be54d16c4475581f00b0b1e3eec8d

    core       bf478630…  ->  685224c9…   (core_check: KINDS content)
    authoring  5c257afe…  ->  0ce31932…   (authoring_check: pack residuals)

## Why the root moved

The surface-silence map (`experiment-2026-10-03-layer-surface-silence.md`)
measured where five conforming implementations of the tool disagree, and
these two seams had ground-truth precedent:

**Pack's residual keywords** (`criteria/authoring_check.py`). After click
A, two independently regrown packs converged to exactly the exercised
keyword surface — and no further. The unexercised remainder that the
CLI's own pack verb drives — `mutation_floor`, `requires`, `by`,
`inputs_manifest`, `environment` — was the named next seam. The check now
calls the full surface and asserts what each does: the mutation floor and
host requirements reach the recipe verbatim; an inputs manifest makes the
claim format 2, names the file, and the file lists each pinned input
beside its digest; `by` lands as producer residue in the ledger, never in
the root; and an `environment` that names no file is refused. (The
`environment` happy path furnishes a dependency set, which can reach the
network — a criterion pins its refusal branch and leaves furnishing to
the environment tests.)

**The step-kind vocabulary** (`criteria/core_check.py`). KINDS was pinned
by type only, so five implementations carried five values — empty, the
two real kinds, and one with invented `sign`/`vendor` kinds — while the
recipe layer above validates every step against it. The check now pins
the content: exactly `{"produce", "gate"}`, the vocabulary the claim
format defines. Widening it is deliberately a format-versioning event
now, not a drift.

## What moved

Two layer checks changed, so two layer roots moved — core and authoring —
and the repository root moved with them; the lockfile records both.
Validated before the reseal: both suites pass against the living
implementation, the kernel chain passes (`kernel_parity`), the closure
criterion and the self-containment test stay green, the full gate
re-earns `REPO_OK` cold at the new root, and the room is refreshed.

## The loop note

These are the first pins whose entire path ran at analysis speed:
measured by an instrument (seconds), named in a record, signed, and
pinned — no producer run, no consumer break, no regrowth needed to find
them. The map that found them can now re-run against future lineages and
show the contraction, the same before/after the pack signature already
exhibits for clicks A/J.
