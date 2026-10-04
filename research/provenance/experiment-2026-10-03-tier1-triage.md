# The tier-1 triage: how far is the quiet map?

*2026-10-03, cycle 13. The question the no-halo cost model forced: each
pin buys one seam, the raw worklist says 268 live seams — is the garden's
end months of signatures away? Instrument:
`research/harness/silence/triage.py`; verdicts in `triage_tier1.json`;
runtime constant comparison across all seven implementations.*

## The answer: zero new pins

The 268 consumed divergences, classified by what actually stands on them
and resolved to runtime truth:

- **197 (73%) are internal-only** — consumed by other generated modules,
  never by the pinned surface. Each lineage is internally coherent, and
  mixed trees are settled as a non-goal, so these are free as a set: one
  declaring sentence in the spec, not 197 clicks.
- **67 are form or alias variance over converged substance.** 28 are
  form-only by construction (parameter names nobody passes, star
  placement no caller crosses). 39 looked like value divergence but were
  re-export mechanics — `= core.MANIFEST` versus the literal versus the
  `os.path.join` expression. Imported and compared at runtime, **eight of
  the nine pinned-consumed constants are byte-identical across all seven
  implementations** (LEDGER, NAMESPACE, RECIPE, SIGN_DIR, SIGN_NAMESPACE,
  STORE, _JAILED, RECORD_NAMESPACE).
- **4 looked substantive; none survive.** Two are facade artifacts (the
  original defines `cli.main`/`cli.verbs` in `_cli/` and re-exports — the
  same attribution the triage already resolves for the kernel). Two are
  **historical echoes cured by signed clicks**: `kernel.MANIFEST` missing
  at runtime from the pre-pin codex trees but present in both r3 trees,
  and the pack keyword gaps present only in g1/r2 generations — no r3
  tree lacks anything. The residue in the current boundary is empty.

## What this means

The surface worklist is not a backlog; it is a *completed audit*. The
closure criterion plus the signed pins already govern everything the
pinned surface stands on, the lineages converge at runtime on all of it,
and the remainder is deliberate freedom — most of it internal, all of it
unconsumed. The measurable distance to the quiet map is exactly:

    the seven staged clicks (timeout direction, rebuild-surface
    reconciliation, scrub canary, verdict vocabulary, audit diet, the
    reference layer, reuse-into-criteria)
  + one spec sentence (sub-layer internals are rebuilt as a set;
    intra-package seams are deliberate freedom)

After that, by the project's own instruments, there is nothing left to
pin that anything stands on — and the remaining work is the endgame:
the clean-room pass, the ceremony, and the stranger.

## Honest limits

The triage trusts the consumption index (static imports and attribute
use); a consumer reaching names dynamically would be invisible — the
same caveat the closure criterion carries. Runtime comparison covered
constants; functions are compared by their exercised behavior, which is
the gates' job and the r3 convergence evidence. And the seven
implementations remain one era's model culture — the stranger clause
stands.
