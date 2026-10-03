# The closure check (click F)

*Research tooling — not normative, not pinned. Its promotion into
`criteria/` is a staged transition for the keyholder.*

The succession's central finding, made testable: **the gate must not
consume what no check exercises.** For every name and keyword a PINNED
file consumes from the generated package, the check of the layer owning
that module must exercise the same — otherwise a conforming implementation
can fail the gate's own machinery, and the gate is not closed over the
equivalence class it names.

    python3 closure_check.py               # judge the working tree
    python3 closure_check.py --rev <rev>   # judge any committed boundary

## Validated against history (2026-10-03)

- At the boundary **before click A** (`5f0f2aa`): 11 violations, including
  the exact seam the succession found the hard way — `selfclaim.py`
  consuming seven `pack` keywords that `authoring_check` never exercised.
  The known caught-and-fixed bug, caught statically.
- **Today**: the pack seam is gone (click A independently confirmed), and
  the check finds **four remaining unexercised consumptions** — pinned
  criteria consume `kernel.MANIFEST`, `kernel.ledger`, `kernel.RECIPE`
  which `kernel_check` does not exercise. Latent, not yet live: every
  regrown kernel so far happens to carry those names — the prior saved
  us, which is exactly the kind of safety this project refuses to rely
  on. Each is a one-line pin candidate.

A regrowth-and-judge cycle takes hours per specimen; this takes seconds
per boundary, over the whole history. It is the hereditary form of the
succession's lesson: the condition under which the judge's own
dependencies survive regrowth.
