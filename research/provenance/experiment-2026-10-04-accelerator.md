# The accelerator: what fourteen cycles say about the loop's dynamics

*2026-10-04, cycle 15 (with the thermodynamics note). Source: the
discovery ledger, the provenance records, and the root timeline. This is
the analysis the ledger was started to make possible — whether the loop
compounds, where it saturates, and how it actually ended.*

## The cost curve: four orders of magnitude in six days

Cost per adoptable counterexample, by era:

    cycles 1–7   (self-rebuild … succession r2)   producer-speed:
                 hours-to-days of producer time per finding
    cycles 8–9   (scaling, shared cache)          mixed: hours, mostly analysis
    cycles 10–14 (instruments era)                analysis-speed:
                 seconds-to-minutes per finding

The thermodynamics note prices the floor: an earn costs ~1 s/layer and a
static sweep covers the whole history in seconds, so once findings came
from instruments instead of regrowths, the unit cost fell by roughly
10³–10⁴. The mechanism is traceable in the ledger, not inferred —
cycle 6's specimens *became* cycle 10's instruments.

## The instrument-origin DAG

    stage 2 (4) ──────────────┐
    ladder (5) ───────────────┼──► silence map (10) ──► surface map (11) ──► triage (13)
    succession (6,7) ─────────┼──► closure check (10) ─► click F (signed) ──► bundle (14)
         │                    │
         └─► clicks A,J ──────┘         scaling (8) ─► reuse/layered audit ─► thermo (15)
                                        shared cache (9) ─► transfer cost measured (15)

Every arrow is a recorded dependency: an experiment's finding that became
the next experiment's tool. No cycle after 9 required a producer run to
*find* anything; producers were only needed to *verify* pins steered
(r3, cycle 12).

## The governor: saturation vs completion

The design separates find-speed (machine) from adopt-speed (one human
signature per root move). The data on adoption:

    find-to-promotion latency:  days (cycle 1–6 era) → same-day (10–14)
    signature throughput observed: five signed transitions in six days
    unsigned queue: peaked ≈ 12 clicks (10-03), EMPTY by 10-04

The question the ledger was built to answer was whether the queue would
grow without bound once finding became free — governor *saturation*, the
takeoff signature. The answer is no, and for the interesting reason:
**the loop hit completion before saturation.** The triage (cycle 13)
found zero new pins owed; the bundle (14) drained the queue; the maps
are quiet. Find-rate fell to zero *for substantive findings* while
signature capacity still had headroom.

## Depletion or compounding? Both — and that is the honest answer

The ledger's falsification section named the competitor hypothesis: a
young codebase is target-rich, so a rising rate might be easy mining
rather than compounding instruments. Fourteen cycles later the curves
separate cleanly: instrument power compounded (each sweep covered more,
faster — closure went from nonexistent to whole-history-in-seconds) AND
the substrate depleted (the surface worklist collapsed under triage to
zero owed pins). The loop did not slow down — it ran its substrate dry
at full speed, which is the success condition, not the failure mode.
Discoveries in cycles 13–15 are increasingly *meta*: verdicts about the
process (the zero-pins verdict, the asymmetry ratios, this note) rather
than seams in the boundary.

## The terminal model

Steady state for a loop like this is `throughput = min(find, adopt)`,
with find compounding and adopt roughly constant at the governor. Three
regimes follow: producer-limited (cycles 1–7), briefly
signature-limited (10-03, when twelve clicks queued against one
signer), and substrate-limited (now — nothing left to find that
anything stands on). A system that *stays* in regime two with a growing
queue is the one the takeoff analysis warned about; this one passed
through it in about a day and exited into regime three. The next
substrate — the only one left — is out-of-distribution: a stranger's
culture, a new model era, a different language. The accelerator is
intact and idle; it is pointed at a field it has finished harvesting.
