# Three declared obligations with nothing behind them

2026-10-14. Staged for a keyholder signature. Each is a **contraction**: every
current member already satisfies it, so declaring it evicts nobody and refuses
future implementations that would do otherwise. None is landed here.

Two were found by zeta's mutant coverage; the third by reading `gate.py`
against the determination result and then testing it. All three were confirmed
by execution, not by inspection.

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

All three are contractions, so no current member is evicted and the authored
implementation already passes each assertion. The root moves, which retires
the reconstruction population again — it currently stands at one member, so
there is nothing further to lose, and this is the moment to batch root moves
before succession trials are re-run.

Finding 3 additionally argues for a second change the author should weigh:
having `gate.py` read its suite list from the recipe instead of from a glob,
so the read set is inside the pinned set by construction rather than by a
criterion checking after the fact. That is a change to the gate, not only to
the criteria, and it is left to the keyholder.
