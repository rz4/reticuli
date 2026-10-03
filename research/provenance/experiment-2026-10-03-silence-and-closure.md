# Two instruments: the silence map, and the closure check

*2026-10-03. Research — nothing here moves a root (`cfb038bf…`
throughout). The deep reading behind both: a boundary's silence is filled
by the prior, and every consumer depends on something the boundary never
said. These instruments make that measurable in seconds instead of
discoverable in producer-hours.*

## 1. The silence map (`research/harness/silence/`)

Independent blind reconstructions implement exactly what the checks
exercise and nothing more — so where N gate-passing implementations
DISAGREE is a direct measurement of the boundary's silence. The
instrument: a generated probe battery over every implementation, divergent
probes clustered by partition (who splits from whom) and delta kind (how).
Each cluster is one unpinned decision, lit up by the model prior itself —
the ratchet made active.

Validated against both ground truths, then it out-discovered them:

- **kvparse (stage-2 C_0 class)**: rediscovers the coercion silence from
  generated probes alone; correctly shows NO duplicates silence (the class
  converged on last-wins — the map measures non-convergence, not
  difference-from-original); and finds **three silences stage 2 never
  saw** — malformed-line handling (180 probes: silently skip vs
  ValueError vs whole-line-as-key), leading-blank handling (one model
  errors on a leading newline), comment lines.
- **confparse (ladder controls)**: resolves six splits mapping onto the
  known intent bits, with the two prior-coincident bits correctly absent.
- **The ratchet, measured as contraction**: the C_0 class shows 242
  divergent probes in 4 silences; the post-ratchet C_1 class shows 192 in
  3 — and the pinned silence (coercion) is GONE from the map. Pinning
  visibly contracts measured silence.

## 2. The closure check (`research/harness/closure/`) — click F, built

The succession's finding made testable: for every name and keyword a
pinned file consumes from the generated package, the owning layer's check
must exercise the same — else a conforming implementation fails the gate's
own machinery. AST over the pinned surface, judged against any committed
boundary (`--rev`).

Validated against history: at the pre-click-A boundary it flags **exactly
the pack seam the succession found by regrowing the whole tool** — all
seven selfclaim keywords against authoring_check — and at today's boundary
that seam is gone (click A independently confirmed). Then it discovered
**four live gaps in seconds**: pinned criteria consume `kernel.MANIFEST`,
`kernel.ledger`, `kernel.RECIPE`, unexercised by kernel_check. Latent, not
yet bitten — every regrown kernel so far happens to carry those names,
i.e. the prior saved us, which is exactly the reliance this project
refuses. Hours of producer regrowth per specimen, replaced by a
seconds-long static sweep over the whole history.

## The staged clicks these produce (keyholder's)

- **Promote the closure check into `criteria/`** (click F proper): closure
  stops being an audit finding and becomes a property the gate enforces.
  One new criterion file; a transition.
- **Pin the four kernel consumptions** (`MANIFEST`, `ledger`, `RECIPE` —
  exercised by kernel_check): three one-line additions; a transition,
  likely bundled with F.
- **From the silence maps**: the malformed-line surface is the dominant
  open silence in both parser subjects (180 probes, three-way split
  including a family that hard-errors). If kvparse/confparse were real
  boundaries, that would be the next C_2 pin; as research subjects it
  stands as the demonstration that the instrument ranks what to pin next.

## Why this is the exponent

Discovery has been running at the speed of producers: hours per regrowth,
one seam per succession. Both instruments move it to the speed of
analysis: seconds per boundary, every seam at once, over the whole
history. The silence map finds what the criteria never said; the closure
check finds what the gate itself depends on without saying; each finding
is a one-line pin; and the C_0→C_1 contraction shows the loop closing
measurably. This is the machinery for the discovery rate the keyholder
predicted.
