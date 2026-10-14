"""Pressure sources. Each yields pressures; none decides anything.

A source is free to be fast, speculative and wrong. It cannot move a verdict,
because what it emits is undeclared until a signature says otherwise, so the
cost of a bad source is wasted compute rather than a corrupted identity. That
asymmetry is what licenses running these in parallel and at agent speed.

  record_surface  the record specification's own validation sentence, put to
                  every document-consuming kernel function.

Planned, each with machinery already built elsewhere in research/:
  composition     consumer substitution and the composition rule run in
                  reverse, starting with the jq arm
  peer            member against member, from the crossjudge harness
  deployment      environment deltas -- interpreter versions, absent tools
"""

from __future__ import annotations

from . import record_surface

REGISTRY = {"record_surface": record_surface}
