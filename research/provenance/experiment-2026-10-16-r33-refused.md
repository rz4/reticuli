# r33 refused: a signed obligation catches its first stranger

2026-10-16. Root `3302eb8a`, frozen before the run. Lineage: `sol56-amazon`
= `gpt-5.6-sol:high@amazon` through the DOE gateway — the previous
generation of the family that qualified as codex, on a different serving
path. **Growth 21/21; condition 3 failed; no trial seals; the closure
count stays at 0 of 3.** Predictions in `predictions_r32.md` and the r33
continuation.

## What happened

The floor probe cleared identity on its first attempt, falsifying the
generational-ladder prediction from the side opposite gemini's: gpt was
above the identity rung at least one generation before gpt-6, so the
crossing point is family-specific in both directions.

The earned full run then grew all 21 layers overnight (P6 held), through a
night of serving-path failures that voided every other lineage — one
genuine capability retry in the whole run. The full gate refused in 1.2
minutes:

```
criteria/obligations_check.py :: the_band_is_closed
AssertionError: the band includes its upper boundary
```

## The defect, measured

The regrown `run.py`:

```python
def _in_band(value, lower=1.5, upper=4.0):
    return ... and lower <= value < upper
```

Closed at the lower boundary, open at the upper. The authored obligation:
the band membership test is closed — a redo whose cost ratio lands exactly
on the tolerance is in band. The specification carries two intervals with
different closure: the tolerance PARAMETER may be set in `[1.5, 4.0)`
(half-open), while the band TEST against a chosen tolerance includes its
boundary. The producer applied the parameter range's shape to the
membership test. A defensible misreading — which is precisely what makes
it a criterion's job to refuse.

## Why this refusal matters more than the others

The clause that caught it was signed 2026-10-14 as one of the five
unpinned obligations — pressure zeta surfaced, a keyholder signed, and the
criteria gained a check that had never existed before this week. r33 is
that signature's first contact with a producer that had never been
measured against it, and it refused the tree in seconds, naming the exact
assertion. The ratchet demonstrably tightened: a boundary learned from one
family's near-miss now stops a different family's actual miss.

## The placement pattern, fourth witness

`the_band_is_closed` lives in the repo-level `obligations_check.py`. The
run layer's own criteria do not test band closure, so the producer
received no signal at the layer that owns `_in_band` and learned of the
refusal at assembly — the same shape as the three instances recorded in
`2026-10-15-layer-local-audit-deep.md`, now with a fourth witness and a
measured price. Candidate: a band-closure line in the run layer's
criteria, batched with the staged root move.

## Predictions resolved, and the accounting

P6 (21/21) held. P7 (no assembly-only refusal) FAILED in the letter —
the refusal was assembly-only — though its mechanism (the layer-18
exchange fixture) was never reached: the gate stops at obligations, so
audit_deep remains unjudged for this tree. P8 held: $15.87 measured
against a $35 bound, 209 calls, with an 88% cache rate on the amazon path
(9.88M cached vs 1.33M fresh input tokens) — the first full run accounted
entirely by in-ledger cost events, reconcilable line by line. P9 held:
the overnight weather voided the other four lineages and never touched
this one's record.

A second attempt is cheap and informative, as r26's was for claude: the
defect is one comparison operator, and the producer was never told. It
would also test whether the misreading is stable in the family or a
sampling accident.
