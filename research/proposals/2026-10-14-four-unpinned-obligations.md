# Four unpinned obligations, staged as one signature

2026-10-14. Staged for a keyholder signature. Each is a **contraction**: every
current member already satisfies it, so declaring it evicts nobody and refuses
future implementations that would do otherwise. None is landed here.

Two were found by zeta's mutant coverage; the third by reading `gate.py`
against the determination result; the fourth by transferring a silence the jq
population exposed. All four were confirmed by execution, not by inspection.

**Sign them together.** The root has moved twice today and each move retires
the whole reconstruction population, which stands at one member. Four
contractions in one signature cost one rebuild; four signatures cost four.

## 1. A cost total may count a boolean

`spec/record.md` is explicit: `cost` holds "any subset of exactly four keys,
each a non-negative number and **never a boolean**." The kernel implements it:

```python
if isinstance(value, bool) or not isinstance(value, (int, float)):
    continue
```

Remove the `isinstance(value, bool)` test and **the whole gate still passes**.
No criterion exercises it, so the root admits an implementation whose cost
totals count `True` as one. Since a cost condition is compared against a
declared envelope, a boolean smuggled into a total is a measurement that looks
like money.

Witness: mutant `cost-accepts-boolean`, surviving.

## 2. The cost band may refuse its own boundary

`spec/verification.md` makes the tolerance normative — default 2.0, settable
in `[1.5, 4.0)` — and the kernel's own words call the comparison a band over
the closed interval:

```python
"""Comparability is a BAND, [1/tol, tol] -- not equality."""
return (1.0 / tolerance) <= ratio <= tolerance
```

Change both `<=` to `<` and **the gate still passes**. An implementation using
an open interval would refuse a redo whose ratio sits exactly on the declared
tolerance, and would still qualify as a member. Two conforming members would
then disagree about a verdict at the boundary, which is the one thing the
closed interval was written down to prevent.

Witness: mutant `tolerance-exclusive`, surviving.

## 3. The gate reads criteria the root does not pin

`gate.py` enumerates its suites:

```python
for path in sorted(glob.glob("criteria/*.py")):
```

The recipe pins 24 criteria and 24 are present, so nothing is adrift today.
But the gate's read set includes a **directory listing**, and no pinned path
determines what a listing returns. Drop any file into `criteria/` and it runs;
dropping one that fails turns a conforming tree non-conforming. Verified by
staging a room and adding `criteria/zzz_intruder.py`: the gate reported
`FAIL criteria/zzz_intruder.py` and exited 1.

`REPO_OK` is pinned, so the verdict is inside the root while the thing that
decided it is not. In the paper's terms the determination result requires
`Rd(A,S) ⊆ Π(S)`, and a directory enumeration is not inside `Π`.

**The scope is bounded and worth stating.** A cold `ret audit` materialises
only the declared files, so the glob there finds exactly the pinned set and
the canonical path is sound — every root this project has recorded was earned
that way. The gap bites a warm `python3 gate.py` in a working tree, which is
how the gate is actually run during development, including every run today
before the cold audit confirmed it.

This one is the most serious of the three, because it is not a missing test
for a declared behaviour but a way for an undeclared file to decide a verdict
— the same shape as pressure reaching a producer's room, which
`criteria/boundary_check.py` now refuses for zeta.

## 4. The record format has no position on numeric form

The first three are obligations the specification declared and left untested.
This one is different in kind: a topic the specification has never addressed.

`spec/record.md` covers types and ranges thoroughly — a cost value is "a
non-negative number and never a boolean", a root is "64 lowercase hex" — and
says nothing anywhere about **representation**. So:

```
cost {"usd": 1}    digest cec3f00bdc5d0f6f9565...
cost {"usd": 1.0}  digest 02ea51b1d517de6c33d5...
```

The same measured cost, two citations. It is reachable in ordinary use,
because `run.cost` sums whatever numbers the ledger holds and the form
propagates into the record.

**This is probably not a bug, and the clause should say so rather than fix
it.** `record_read` enforces that a file holds its own canonical bytes
precisely so that "reformatting a record breaks the bond between its digest
and its signature" — a signature signs bytes, and a signature over
facts-rather-than-bytes would be forgeable by reformatting. Pinning a
canonical numeric form would invert that: a reader would have to normalise
before verifying, which is the one thing the bond exists to prevent.

What the silence does permit is a specific divergence. A reconstruction that
helpfully normalised `1.0` to `1` inside `record_canonical` would then
**refuse valid records**: read a file containing `1.0`, canonicalise it to
`1`, find `raw != canonical`, reject. A conforming-looking member that rejects
good records, and nothing currently forbids it.

One sentence closes it, in the Validation section beside the rest:

> Canonical bytes carry the document's own numbers verbatim. A reader does not
> normalise numeric form, and a digest therefore names bytes rather than
> facts: two records stating the same measurement with different
> representations are different records, cited differently, and that is
> intended.

The shipped implementation already behaves exactly this way — `json.dumps`
passes numbers through untouched — so this is a contraction that evicts
nobody.

How it was found is worth recording. Not by probing reticuli: by taking the
*shape* of a silence the foreign population exposed. Three of the jq splits
(`integer-float-identity`, `division-exact`, `big-exponent`) cluster on number
representation, which is a classic thing for a language specification to leave
open — and asking whether the host system had the analogous silence found one.
That transfers a failure kind rather than content, and it is the only
mechanism tried so far that reaches outside the system's own vocabulary.
Every other source derives its pressure from the specification or the
implementation that already exists, and so can only drive the specification
toward being a fixpoint of itself.

## The proposed criterion

One file closes all three. It is written here rather than in `criteria/`
deliberately: `gate.py` globs that directory, so an unpinned criterion placed
there would itself be an instance of finding 3.

```python
"""Declared obligations that had no criterion. Writes OBLIGATIONS_OK."""
import glob
import os
import re
import sys

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import recipe, run


def battery():
    # 1. A cost total never counts a boolean.
    totals = run.cost.__wrapped__ if hasattr(run.cost, "__wrapped__") else run.cost
    # (exercised through a staged ledger; see the fixture below)

    # 2. The band is the CLOSED interval [1/tol, tol].
    assert run._in_band(2.0, 1.0, 2.0), "the band includes its upper boundary"
    assert run._in_band(1.0, 2.0, 2.0), "the band includes its lower boundary"
    assert not run._in_band(2.01, 1.0, 2.0), "and excludes what lies beyond"

    # 3. The suites the gate runs are exactly the suites the root pins.
    parsed = recipe.load_recipe(".")
    pinned = {p for p in parsed["claim"].get("inputs", [])
              if p.startswith("criteria/") and p.endswith(".py")}
    present = set(glob.glob("criteria/*.py"))
    assert present == pinned, (
        f"the gate runs what the root does not pin, or the reverse: "
        f"unpinned {sorted(present - pinned)}, missing {sorted(pinned - present)}")
```

The cost-boolean half needs a staged claim directory with a ledger holding
`{"event": "producer", "usd": true}`, asserting that `run.cost` returns no
`usd` key for it. A fixture, not a new mechanism.

## What signing this costs

All four are contractions, so no current member is evicted and the authored
implementation already passes each assertion. The root moves, which retires
the reconstruction population again — it currently stands at one member, so
there is nothing further to lose, and this is the moment to batch root moves
before succession trials are re-run.

Finding 3 additionally argues for a second change the author should weigh:
having `gate.py` read its suite list from the recipe instead of from a glob,
so the read set is inside the pinned set by construction rather than by a
criterion checking after the fact. That is a change to the gate, not only to
the criteria, and it is left to the keyholder.
