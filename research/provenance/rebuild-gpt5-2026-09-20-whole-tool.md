# The whole tool regrows, layer by layer — twelve of thirteen

*Research record — what was tried and what it showed. Not normative.*

Following the kernel-chain result (`rebuild-gpt5-2026-09-20-kernel-chain.md`),
this rebuilds the rest of reticuli the same way: for each remaining layer,
`ret rebuild <chain>/<layer> --producer openai` reuses the sealed layers below
(the incremental primitive) and asks gpt-5 to regrow only that layer's own
modules from its acceptance suite. Together with the kernel run, this covers the
entire self-hosting tower.

## Result: twelve of thirteen layers regrow to their exact roots

| layer | modules regrown | converged | cost |
|---|---|---|---|
| core | 1 | ✓ root match | $0.05 |
| recipe | 1 | ✓ | $0.12 |
| identity | 1 | ✓ (80 turns) | $2.35 |
| seal | 1 | ✓ | $0.18 |
| run | 1 | ✓ | $0.24 |
| build | 1 | ✓ | $0.42 |
| attest | 1 | ✓ | $0.69 |
| crosscheck | 1 | ✓ | $9.70 |
| exchange | 5 (_util, registry, transfer, attest, record) | ✓ | $14.09 |
| authoring | 4 (render, authoring, feedback, pack) | ✓ | $5.06 |
| agents | 1 (hooks) | ✓ | $4.31 |
| launcher | 1 (launcher) | ✓ | $3.07 |
| **surface** | 5 (assess, heldout, reuse, **cli**, __main__) | **✗ capped** | (uncounted) |
| **total** | | **12 / 13** | **$40.27** recorded |

Every converged layer verified and (for the behavioral ones) crosscheck-accept,
in different, mostly-leaner code. Multi-module layers regrow as readily as
single-module ones: `exchange` (five modules, ~1,200 lines including the 465-line
registry) and `authoring` (four modules, ~1,000 lines) both landed their roots.

## The one that did not: surface, and why it is the kernel's twin

`surface` did not converge. gpt-5 got `cli.py` to 840 of 2,574 lines (with stub
modules for the rest) before the 18-minute cap. This is exactly the shape of the
kernel monolith two nights ago: a single ~2,560-line module is not
one-shot-regrowable. `cli.py` is the twin of the old `kernel.py`, and the remedy
is the one that already worked — **decompose `surface` into sub-claims** (the CLI
verb groups are the obvious seam: authoring / verification / reconstruction /
evidence / transport, plus the render and assess modules as their own layers),
then regrow each cheaply. That is the clear next piece of work.

## What this establishes

- **The decomposition-plus-reuse workflow generalizes past the kernel to the
  whole tool.** Twelve of thirteen layers of reticuli's own tower regrow from
  their criteria alone, by an independent producer, for about forty dollars —
  and the four cheapest for under a dollar.
- **The remaining frontier is a size problem, not a thesis problem.** Every layer
  small enough regrows; the only holdout is the one oversized module, and the
  cure is known. Reticuli can now largely rebuild itself, and the path to
  rebuilding all of itself is a mechanical continuation of what is already done.
- **The same two caveats hold** (see the kernel-chain record): byte-exact
  serialization is the expensive floor (identity), and a layer regrows to its
  check's strength, so leaner suites yield leaner-but-conformant modules that the
  composite `kernel_check`/deep-audit still hold to full behavior.

The honest headline: reticuli is now, empirically, a tool that an independent
model can regrow from its own published criteria — all of it but one oversized
module, and that module's fix is the decomposition this whole arc demonstrated.
