"""Pressure sources. Each yields pressures; none decides anything.

A source is free to be fast, speculative and wrong. It cannot move a verdict,
because what it emits is undeclared until a signature says otherwise, so the
cost of a bad source is wasted compute rather than a corrupted identity. That
asymmetry is what licenses running these in parallel and at agent speed.

  record_surface  the record specification's own validation sentence, put to
                  every document-consuming kernel function.
  jq_surface      the jq language, put to three independent implementations
                  nobody here wrote: the control for author-lineage
                  contamination in the reticuli population.
  consumer_surface  a consumer claim as oracle over realizations of a
                  dependency it relies on: all-break is repair, a split is
                  eviction. The machine form of the substitution finding, and
                  the only non-circular test of whether a rebuild can replace
                  the original -- the consumer, not a probe, is ground truth.

  transfer        silences carried by SHAPE from the foreign population: the
                  only source that can reach outside this system's own
                  vocabulary, and the only one whose findings may claim the
                  fourth rung. Everything else -- probes read out of the spec,
                  mutants made by perturbing the implementation -- can at most
                  drive the specification toward being a fixpoint of itself.

Deployment pressure is not a source but a population -- the authored bytes
under each interpreter the claim's host contract admits -- so it reuses the
sources above. See population.deployment.

Planned, with machinery already built elsewhere in research/:
  composition     the composition rule run in reverse, from substitution/
  peer            member against member, from the crossjudge harness
"""

from __future__ import annotations

from . import consumer_surface
from . import jq_surface
from . import record_surface
from . import transfer

REGISTRY = {"consumer_surface": consumer_surface,
            "jq_surface": jq_surface,
            "record_surface": record_surface,
            "transfer": transfer}
