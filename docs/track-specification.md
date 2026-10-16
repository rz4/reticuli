# I want to reconstruct, and improve the specification

This track is for the reader who wants the full loop: not just
implementations regrown from a specification, but the specification itself
*learning* from the regrowths. It assumes the first two tracks — you know
what a claim is, and you have producers that can rebuild one.

**What you can do at the end:** maintain a population of independently
reconstructed implementations; measure where they disagree — which is
precisely where your specification is silent; convert those silences into
reviewed, signed amendments; and keep the whole loop honest while agents
generate most of the raw material.

## The idea in one paragraph

Independent blind reconstructions implement exactly what the criteria
exercise and nothing more. So where N gate-passing implementations
*disagree*, the boundary was silent — and the disagreement is a direct
measurement of the silence, obtained without waiting for a user to be
surprised by it. Pinning a silence contracts the measured map; the next
round of reconstruction probes what remains. The specification converges
toward carrying the software completely, and every step of the convergence
is evidence, not opinion.

## The journey

1. **[The process](process.md)**, section 6 — the outer loop and its
   vocabulary: populations, pressure, the queue, and the signature as the
   only operation that changes obligations.
2. **[Zeta internals](zeta.md)** — the exploratory instrument in detail:
   how findings are classified by the cost of adopting them, how a
   finding's strength is laddered, why the probe battery carries a live
   positive control, and why every queued finding packages its own
   machinery for independent replay.
3. **[Transitions](transitions.md)** — what actually happens at a root
   move: the old population retires, membership is re-earned, and the
   repository's history records why.
4. **The annotated implementation** — for this track the book is not
   optional reading: [`zeta.lib.split`](book/zeta/zeta.lib.split.md) and
   [`zeta.lib.entry`](book/zeta/zeta.lib.entry.md) are where
   classification and portability are enforced, and
   [`reticuli._kernel.crosscheck`](book/reticuli/reticuli._kernel.crosscheck.md)
   is the three-machine test as executable fact.
5. **[Design rationale](design-rationale/README.md)** and the research
   record — the measured history: what each instrument got wrong before it
   got right, kept deliberately, because an instrument's error history is
   part of its calibration.

## The discipline that holds it together

Three rules keep an agent-accelerated specification loop from eating
itself, and each is enforced by machinery rather than by vigilance:

- **Provenance before novelty.** A system cannot assert novelty about its
  own vocabulary. Findings carried in from foreign populations name where
  they came from and what silence they expose, or they cannot claim to be
  more than sightings.
- **Replay before belief.** A finding that cannot be reproduced cold, by
  machinery that trusts nothing about its discoverer, is not a finding.
- **Signature before force.** Nothing an agent or an instrument produces
  binds anyone until a person signs it — and everything a signature adopts
  was reproducible by that person first.

## Where this track ends

It doesn't, by design. The loop's fixed point — a specification whose
reconstructions no longer disagree anywhere the criteria can see — recedes
as the probes improve, and the distance to it is itself the measurement:
how much of your software your specification actually carries today.
