# The seal — a claim whose unpinned surface is visible to the eye

*2026-09-29. Research record — nothing here is normative, and no root moved.*

`research/harness/seal/claims/S` (root `3d65990b…`) is a claim for a
constellation renderer: `render(root) -> SVG` turns any 64-hex claim root
into a small star map — the root made visible, so "the name did not move"
can be *seen*. The check pins the geometry as the contract: star count and
positions derived from the hash bytes, the closed ring joining them sorted
by angle around their centroid, the 256×256 canvas, one `<circle>` per
star and one `<line>` per edge within tolerance, determinism, and
distinctness across roots. Everything else — color, radius, stroke,
background, decoration — is deliberately left as the renderer's own.

The stage-2 protocol, run on this visual subject: six blind rebuilds from
the check alone (3 codex, 3 Claude Code). **Six of six converged**, each
re-earning the claim's root. For one fixed input root, all six draw the
same sky — the pinned surface held unanimously — and no two dress it the
same way (`styling.json`: six palettes, radii from 2 to 3, stroke widths
from 0.6 to 1, one renderer adding `<g>`/`<title>` structure, one drawing
bare black-on-transparent). Even the styling shows the prior at work:
three independent renderers chose a dark navy ground for a constellation
unprompted, two of them within two hex digits of each other.

Read against the ladder record of the same day: this is the constructive
half. When a check pins exactly what the claim means and stays silent
only where difference is welcome, blind cross-family regrowth agrees on
all of the former and none of the latter. The boundary decides what
converges; the seal's boundary was drawn on purpose, and the convergence
followed it.

The reference renderer is `claims/S/seal.py`; the regrown ones are
`impls/`. `run_seal.py --report` re-renders one root through all of them.
