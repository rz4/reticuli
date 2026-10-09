# Proposal — a declared data dependency re-earns its content match

*Staged 2026-10-09, from the corpus performance assay — the first seam
selected by an instrument rather than a trial. A criteria edit AND an
implementation fix (the shipped tool false-passes too), so a root move
plus a src change; staged for the keyholder. Witness measured against
every realization before staging.*

## The finding

A component link has two species. A CODE component supplies produce
outputs (`from = "<component>"` steps): the deep audit re-earns its gate
on the dependent's shipped bytes, and exchange_check pins exactly this
(break the shipped lib.py; the composed verdict refuses). A DATA
dependency is the other species: `detect_components` content-matches a
pinned INPUT against a component's output at seal time and `seal_with`
records the attribution — but there is no `from` step, and NOTHING
re-earns the content match afterward.

The witness: seal a component whose gate produces `data.txt`; seal a
dependent that pins `data.txt` as an input and declares the attribution
(the pulled-data shape); then FORGE the dependent's `data.txt` and
reseal. The dependent now ships bytes that do not match the component it
attributes them to, and the attribution rides in its manifest — which
`sign_root` folds into signed chain identity. Measured 2026-10-09:

    verify:      True
    audit:       True
    audit_deep:  True     (gen0 walks the component, re-earns its gate
                           IN ISOLATION — supplied={} since there are no
                           produce steps — and reports ok)
    deps edge:   "ok"     (resolve-by-root presence, not content)

Every realization false-passes: gen0 (the shipped tool), r9, r14, r17,
r18. "Gates compose, verdicts never carry" holds for code components
and silently does not for data components — the unexercised half of a
symmetric pair, where the exercised half (code) has been pinned since
the transitivity fixture and the data half has never had a fixture.

A second, related divergence surfaced by the same probe: r17 enumerates
the chain from the recipe's `from` fields alone, ignoring manifest-only
components entirely (walks zero layers where gen0 walks one). The
boundary never says WHICH source of truth names the chain — the
manifest's `components` or the recipe's `from` fields — because every
fixture makes them agree. The pin below forces the manifest reading and
covers both findings with one fixture.

## What to pin

The composed audit must re-earn EVERY declared component link on the
bytes the dependent ships — for a data dependency, that means the
shipped input's content matches the resolved component's corresponding
output (re-earned from the component's own gate, not compared against a
carried hash). The witness above becomes the fixture: the clean claim
audits deep ok; the forged reseal is REFUSED with the component named.

## Costs, stated

- The shipped implementation fails the fixture today, so this is a
  criteria edit plus a src fix landing together (precedent: the three
  soundness gaps of 2026-09-28). The root moves.
- By the ratchet rule, adoption resets the qualifying count (currently
  1 of 3, r17) — one more reason for the batched boundary move already
  under discussion: land this, flat-store resolution, and anything else
  accepted, in ONE reset.

## Why an instrument found it

The performance assay timed `audit_deep` across all realizations; r17's
0.000 and two half-times were timing anomalies that unwound into the
walker divergence and then the forgery witness. Discovery at
analysis-speed, from the corpus — the instrument-recursion thesis
demonstrated on its first outing.

## Status

STAGED. Not landed. Witness script preserved in the record; fixture
encodes directly in exchange_check beside the code-component forgery
fixture it mirrors.
