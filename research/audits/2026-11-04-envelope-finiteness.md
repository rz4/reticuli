# A declared cost ceiling may be infinite

*2026-11-04. A third outside review, three findings. One is a defect and is
recorded here; two are correct readings of documented behaviour and are
recorded as proposals at the end. All three were reproduced.*

## The defect

`[claim] envelope` declares the cost ceilings a redo commits to. The
validator in `_kernel/recipe.py` requires each ceiling to be a non-boolean
number greater than zero, and **does not require it to be finite**:

```python
if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) \
        or ceiling <= 0:
    raise ClaimError(...)
```

TOML admits `inf` and `nan` as float literals, and `tomllib` parses them, so
both reach that test and pass it. `-inf` is refused, but only incidentally,
by `<= 0`.

| declared | parses | `paid <= declared` for any finite spend | effect |
|---|---|---|---|
| `usd = inf` | yes | always `True` | a published ceiling that **nothing can exceed** |
| `usd = nan` | yes | always `False` | a published ceiling that **nothing can satisfy** |

Measured: with `usd = inf`, a spend of `1e308` is `within`. With `usd = nan`,
a spend of `0.01` is not.

The first is the consequential one. A claim can publish an apparently hard
budget commitment — the thing the cost envelope exists to make binding, so
that "reproducible" cannot be satisfied by a reproduction nobody could afford
— and impose no finite limit at all. Nothing in the record distinguishes it
from a real ceiling.

## The lineage, which is the interesting part

This is the unexercised half of a contract whose other half is already
closed, which `findings/self-hosting.md` reports is what **every** boundary
repair in this project has been.

Finiteness is enforced in three places:

| where | what |
|---|---|
| `_kernel/attest.py:173` | a **record's** cost value |
| `_kernel/run.py:740` | a **measured** cost from a producer |
| `_kernel/recipe.py:194` | a declared `tolerance` or `mutation_floor` |

The closure ledger dates the first of these: *"2026-10-14, `1d9ab7ed` →
`f9b292af`, **a cost value is finite** — the first gene a RECONSTRUCTION
forced, from r25's own divergence."* Finiteness was learned on the
**measurement** side and never applied to the **declaration** side.

The third is thirty lines below the envelope check, in the same function,
added on 2026-10-29. The comment introducing it reads:

> `envelope` has always refused a damaged table at parse; `tolerance` and
> `mutation_floor` are hard conditions of the same kind and were taken on
> faith…

The envelope was treated as the exemplar the new checks were modelled on. It
was the exemplar for *type* and *sign*. The new checks added *finiteness* on
top, and nobody went back.

So a repair that generalised a rule left the case it generalised from behind.

## Disposition

The fix itself is one clause: require `math.isfinite(ceiling)`, with a
message matching the one `tolerance` already produces.

What it costs is not one clause. `recipe.py` is generated and outside the
root, so editing it moves the build digest and stales the signature. But a
validation rule the claim relies on belongs pinned, which means a criterion,
which means the root moves and the full transition procedure applies —
exactly as the 2026-10-29 batch did for `tolerance` and `mutation_floor`.
Conformance vectors for `inf` and `nan` are pinned too.

So this is a small, well-understood, identity-bearing change. Not patched
here.

Worth folding into the same ceremony as the format-6 question in
`2026-11-04-identity-semantics.md`, since both touch the specification and a
root moves once either way.

## Two proposals, on documented behaviour rather than defects

### `blind = true` is a statement about a mechanism, not a boundary

`_kernel/build.py:709` computes `"blind": not bool(produce_from)`, and the
producer runs as an ordinary shell command — `_run([_SHELL, "-c", command],
cwd=dest, …)` — with no filesystem isolation. So `blind = true` records that
the source-reuse mechanism was not used. It does not establish that the
producer had no other readable path to the original implementation.

This is exactly what `docs/threat-model.md` already says: *"Not
independence… Recorded as a declaration, never proven."* It is not an
undisclosed gap.

The review's proposal is still an improvement, because the single field is
easy to over-read when interpreting an M3 result:

| field | what it would establish |
|---|---|
| `source_reuse = false` | the implementation-copying mechanism was not used |
| `source_isolation = enforced` | the producer had no permitted read path to the original |

The second needs real enforcement — a separate machine, or a restricted
filesystem namespace — plus the isolation configuration recorded as evidence.
Splitting the field without enforcing the second is worse than one honest
field, so the two must land together.

### A `--require-sandbox` mode

Where no sandbox backend is available, `_kernel/run.py` reports `"none"` and
the gate still runs. `docs/threat-model.md` states this plainly, and the
ledger records the backend either way, so a verdict never lies about it.

For a verifier on a shared system judging an unfamiliar claim, reporting
honestly is not the same as refusing. A `--require-sandbox` flag that exits
rather than executing when confinement is unavailable would let a cautious
operator make that a precondition instead of a thing to notice afterwards.

Neither proposal is pinned behaviour today, and both are ordinary
engineering rather than identity changes — except that `--require-sandbox`
would want a criterion if it is to be relied on.
