# The surface silence of reticuli's own layers

*2026-10-03, keyholder-directed run ("run the silence map on the reticuli
layers themselves"). Research — nothing here moves a root (`03edfbb7…`
throughout). Instrument: `research/harness/silence/surface_silence.py`;
map: `map_layers.json`.*

## The measurement

A layer's behavior surface is its API, and the repository holds five
complete gate-passing implementations of every module: the shipped source
and four blind lineages (two families, before and after clicks A/J). The
instrument extracts each module's top-level surface (functions with full
signatures, constants with values, classes) across all five, ranks every
divergent item by consumption (pinned files plus the shipped package's own
internal imports), and reports:

    987 divergent surface items across 37 modules —
    262 consumed (live seams), 163 public unconsumed, 562 private

## Validation: all four seams the succession paid producer-days for

- **`kernel.rebuild`** (11 consumers): four different conforming
  signatures; none carries `guidance`/`producer_env`; one lineage invented
  `without_guidance=`. The spec/check/original three-way disagreement,
  now shown as a five-way spread.
- **`pack.pack`** (6 consumers): the ratchet caught in the act. The
  pre-click lineages are bare-positional — the exact click-A failure. The
  two post-click lineages **independently converged to the identical
  signature**, `(root, name, generated, inputs, gate, gate_output, *,
  envelope=·, claim_format=·, component=·)` — byte-for-byte across vendor
  families: a pinned surface reproduces exactly; everything else floats.
  And the original's remaining keywords (`mutation_floor`, `requires`,
  `by`, `inputs_manifest`, `environment`) sit outside that convergence —
  the predicted next seam, named before it bites.
- **`_kernel.recipe._inputs`** (3 consumers): the 1-arg/2-arg split that
  broke mixed trees, rediscovered; one post-click lineage drifted back to
  the original's two-argument shape unprompted.
- **`_kernel.core.KINDS`**: five implementations, five vocabularies —
  `frozenset()`, `{'produce','gate'}` twice (one as a tuple), and
  `{'produce','gate','sign','vendor'}` (a lineage that invented step
  kinds). The post-click claude lineage matches the original exactly.

Producer-days of succession work, re-derived in seconds — and the
contraction from clicks A/J is *visible in the map* as cross-family
convergence on precisely the exercised surface.

## What is new

The 262 tier-1 items are the complete, ranked worklist for proposal
specimen D (the unpinned seams): every consumed name on which five
conforming implementations disagree, with its consumers attached. The
dozen heaviest (by consumer count) are the natural next clicks; the
`pack` residual keywords and the `KINDS` vocabulary are the two with
ground-truth precedent. Tier 2 (163 public, unconsumed) is deliberate
freedom until something consumes it; tier 3 (562 private) is the
measured size of the class's internal variation.

## Honest limits

Surface, not behavior: identical signatures can still act differently
(the behavioral map covers that for probeable subjects). Facade
placement is reported literally — the original defines `rebuild` in
`_kernel.build` and re-exports through `kernel`, the lineages define it
directly, and the map shows both facts rather than resolving re-exports.
The consumption index is approximate (static imports and attribute use).
And the counting discipline stands: 262 seams are 262 *measurements*;
they become discoveries only as each is staged with a concrete pin.
