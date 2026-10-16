# I need reproducibility in agent work

This track is for the reader whose code is increasingly written by models:
coding agents on laptops, producers behind gateways, CI that has to say
something honest about output nobody line-reviewed. The question the track
answers is not "how do I run agents" but "what, exactly, did I verify
before I merged what one wrote?"

**What you can do at the end:** run any agent as a producer whose output is
judged by machinery it cannot influence; probe cheaply whether a given
model can do the work at all before spending on it; keep cost and failure
accounting that survives contact with providers; review machine-written
pull requests by holding the criteria, not the candidate, to account.

## The journey

1. **[Working with agents](agents.md)** — the inversion the whole track
   rests on: the criteria are the asset, implementations are candidates,
   and candidates are regenerated, compared, and discarded. Producers,
   rooms, the scrub; what was measured about model capability and cost.
2. **[Writing criteria that carry software](criteria.md)** — the craft.
   Reproducibility by agents is exactly as good as the criteria are
   sufficient, and sufficiency has been measured: this page is the four
   lessons, each with the experiment that taught it.
3. **[Producing](producers.md)** — the producer contract in detail: the
   environment protocol, usage reporting, writing an adapter for a new
   model or gateway.
4. **[GitHub and CI](github.md)** — the ecosystem half: what a green check
   establishes, the three kinds of diff, and the review discipline that
   makes agent-authored pull requests tractable.

## The honest caveats, up front

Reconstruction is a *capability* question before it is a workflow question:
some models cannot re-derive software from criteria at any price you would
pay, and price does not predict which. Probe before you commit — a
three-stage probe costs cents and predicts whether a multi-hour run is
worth starting. And treat every failure as unclassified until proven
otherwise: a throttled gateway, a refused request, and a wrong answer must
land in different columns, or your capability table quietly becomes a log
of your provider's bad days.

## Where this track ends

When reconstruction works, it starts returning information: places where
two valid implementations *disagree* are places your specification is
silent. Using that signal deliberately is the third track —
[reconstructing and improving the specification](track-specification.md).
