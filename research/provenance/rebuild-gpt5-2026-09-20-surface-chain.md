# The decomposed surface regrows: 17 of reticuli's 18 layers rebuild

*Research record — what was tried and what it showed. Not normative.*

The final rebuild experiment. With `surface` decomposed into six sub-claims, this
regrows each with gpt-5 (reuse primitive: reuse the sealed chain below, regrow
only this layer). Together with the kernel chain (8/8) and the mid-layers
(exchange/authoring/agents/launcher), it covers the whole tool.

## Result: five of six surface layers converge

Each converged layer rebuilt to its **exact sealed root** (verified), in
dramatically leaner code:

| surface layer | modules (ours → gpt-5) | converged | cost |
|---|---|---|---|
| measure | assess 287→54, heldout 401→11, reuse 110→99 | ✓ | $5.69 |
| cli-base | output 132→61, views 181→50 | ✓ | $6.98 |
| cli-render | report 488→135, statusview 255→91 | ✓ | $0.37 |
| cli-handlers | handlers 192→87 | ✓ | $8.60 |
| cli-parser | parser 774→**108** | ✓ | $6.00 |
| **surface** | dispatch 798 → **448 partial** | **✗ capped** | (uncounted) |
| total | | 5/6 | $27.64 recorded |

Across all 18 layers — kernel (8/8, $13.75), exchange/authoring/agents/launcher
(4/4, ~$26), surface (5/6) — **17 of 18 layers of reticuli regrow from their
criteria alone, by an independent producer.**

## The one holdout is the integration hub, and it is the gate, not the size

`surface` (the dispatch layer) did not converge. This is the sharpest result of
the whole arc, because it is **not a size problem**: `cli-parser` (776 lines)
converged for $6, while `surface`/dispatch (798 lines) did not. The difference is
the **check**. Every other layer has a focused suite; the dispatch layer is held
to `surface_check` — the comprehensive CLI battery that drives every verb end to
end, including rebuild, crosscheck, mutation, and the record. Regrowing dispatch
to satisfy that is regrowing the whole tool's observable behavior at once. It is
the irreducible integration point, and holding it to the full battery is correct
design, not a flaw. (The kernel's twin of this is the crosscheck layer, which
*did* converge for $9.70 — dispatch's battery is heavier still.)

## The finding this makes unmissable: a layer regrows to its check's strength

The converged surface modules are a fraction of ours — parser 774→108, heldout
401→11, assess 287→54 — because their layer checks are focused, so gpt-5 writes
the *minimum* that passes them. That is the equivalence class working exactly as
promised: the root names the criterion, and a leaner implementation that meets
the criterion earns the same root. But it means "regrew to the root" is
"satisfies that layer's check," not "is a full-fidelity module." The comprehensive
gates — `kernel_check` at the kernel's top, `surface_check` at the surface's top,
and the deep audit over the assembled chain — are what still hold the whole tool
to full behavior. **The strength of a check is the knob for regrowth fidelity, and
the honest lesson is: pin what you need held, because a producer will give you
exactly the criterion and no more.** Tightening the per-layer checks toward the
comprehensive ones is the path to full-fidelity per-layer regrowth, at higher
regrow cost.

## A cost note for deep chains

The surface layers cost more than the kernel ones of similar size (cli-handlers,
194 lines, cost $8.60) because the producer **re-reads the entire reused context**
— twelve-plus layers of supplied modules — on every rebuild. Reuse saves
regeneration, not reading; per-layer cost scales with chain depth, not just target
size. For a deep tower this is the dominant cost, and worth designing around
(e.g., summarizing or narrowing the supplied context).

## The whole arc, closed

Two nights ago the kernel would not regrow as a 2,560-line monolith at any price.
Decomposed, the kernel regrew 8/8, and now the surface regrows 5/6 — 17 of 18
layers of reticuli, rebuilt from criteria by an independent model, for on the
order of $70 total. The single holdout is the integration hub, and its
non-convergence is a precise, expected consequence of holding it to the full
acceptance battery. Reticuli can regrow essentially all of itself; the last piece
is the one it is right to make hardest.
