# The constellation seal

*Research tooling — not normative, not pinned.*

A claim root made visible: `claims/S` is a sealed claim for
`render(root) -> SVG`, drawing any 64-hex root as a small star map. The
check pins the geometry — star count and positions from the hash bytes,
the closed ring sorted by angle around the centroid, the 256×256 canvas,
one circle per star, one line per edge, determinism, distinctness across
roots — and deliberately leaves every visual choice beyond geometry to
the renderer. Same root, same sky; different renderer, different weather.

`run_seal.py` regrows the renderer blind through both producer families
(the stage-2 protocol on a visual subject) and re-renders one root
through every reconstruction; `styling.json` records how each family
dressed the same stars. Result 2026-09-29: 6/6 converged, all re-earning
the claim's root — the pinned surface unanimous, the styling never
repeated. The record:
`research/provenance/rebuild-2026-09-29-seal-regrowth.md`.
