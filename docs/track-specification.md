# Track 3: reconstruct and improve the specification

Scope: the full loop. Implementations regrown from the specification;
the specification amended from where the regrowths disagree. Assumes
tracks 1 and 2.

Outcome: maintain a population of independent reconstructions; measure
where they disagree (= where the specification is silent); convert
silences into reviewed, signed amendments; keep the loop verifiable while
agents generate most of the raw material.

## Mechanism

Blind reconstructions implement what the criteria exercise and nothing
more. Where N gate-passing implementations disagree, the criteria were
silent; the disagreement is a direct measurement of the silence. Pinning a
silence contracts the measured map; the next reconstruction round probes
the remainder. Validated here against known ground truth: the instrument
rediscovered every planted silence in a controlled class, reported no
silence where implementations had converged, and found three silences the
authors had not seen.

## Order

1. [The process](process.md), §6 — populations, pressure, queue,
   signature.
2. [Zeta internals](zeta.md) — lanes, rungs, coverage with positive
   controls, entry portability, selection.
3. [Transitions](transitions.md) — root moves: retirement,
   re-qualification, history.
4. The annotated implementation —
   [`zeta.lib.split`](book/zeta/zeta.lib.split.md) (classification),
   [`zeta.lib.entry`](book/zeta/zeta.lib.entry.md) (portability),
   [`reticuli._kernel.crosscheck`](book/reticuli/reticuli._kernel.crosscheck.md)
   (the three-machine test).
5. [Design rationale](design-rationale/README.md) and the research record
   under `research/` — including the instrument's own error history.

## Invariants

1. Provenance before novelty. A finding imported from a foreign population
   names the source and the silence, or it is at most a sighting.
2. Replay before belief. A finding that does not reproduce cold, under
   machinery that trusts nothing about its discoverer, is not a finding.
3. Signature before force. No output binds anyone until a person signs
   it, and everything adopted was reproducible by the signer first.

Termination: none. The measured distance between the specification and its
reconstructions is the standing answer to "how much of this software does
the specification carry."
