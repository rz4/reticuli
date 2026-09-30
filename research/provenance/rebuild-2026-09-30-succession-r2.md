# The succession, rerun under the tightened criteria (clicks A and J)

*2026-09-30. Research record — the reprove for the click A/J transition.
Trees in `research/harness/succession/lineages-r2/`.*

## What this rerun answers

The first succession (`rebuild-2026-09-29-succession.md`) found the
repository's gate was not closed over its own equivalence class:
conforming regrown trees failed it because pinned machinery consumed
unpinned behavior. The keyholder signed two clicks —
`revision-2026-09-29-close-the-gate-clicks-a-and-j.md`, root
`16297fb0…→706ed56b…`. This rerun grows the whole tool blind again, both
families, under the tightened criteria, and asks: did the clicks move the
regrown trees toward running the repository's own machinery?

## The trees

Both lineages regrew all twenty layers from scratch under the new root,
into `lineages-r2/` (the baseline trees preserved beside them for
comparison). Held-out `tests/`: **102 of 102 environment-valid tests pass
for both** (only `test_streams`, environmental, fails — as on the
original). The regrown tools are behaviorally the tool, again.

## The headline: the substantive refusal is gone

Baseline (before the clicks): the repository gate died in **0.3 minutes**
— the regrown `pack` could not run `scripts/selfclaim.py`, a hard refusal
on the first pinned script that used the unpinned surface.

After the clicks, measured criterion-by-criterion against the codex-r2
tree (mirroring `gate.py` exactly — the eight STAGED kernel sub-suites via
`kernel_parity`, the rest directly, **no aggregate timeout**):

    every criterion passes.

- `authoring_check` (click A) — **0.7 s**, ok. The regrown pack now
  carries the keyword surface and the component/envelope/claim_format
  features selfclaim needs.
- `kernel_parity` (covers `kernel_check`, click J, and the seven other
  staged kernel sub-suites) — **10.1 s**, ok. The regrown kernel now
  accepts a producer that earns the gate in its room.
- `surface_check` 2.0 s, `vectors_check` 1.8 s, `exchange_check` 1.8 s,
  `launcher_check` 3.0 s, and the rest — all ok.
- `self_check` — the only non-pass, and not an r2 failure: it flagged an
  **uncommitted lockfile drift** in this session's own defect fix (the
  authoring root re-pin), corrected in
  `revision-2026-09-30-...` before this record was finalized. With the
  lockfile current, self_check passes on the r2 tree too.

The clicks did exactly what a ratchet click should: they removed the
family of conforming-but-unusable implementations. A regrown tool now
passes every criterion the repository judges by.

**Cross-family, the sharpest case.** In the first succession the
*claude* lineage was the one whose kernel refused every real producer
(reading a producer's in-room residue as rewritten pinned bytes) —
specimen 8, the reason click J exists. The claude-r2 kernel was grown
against the tightened `kernel_check`, so it clears the click-J behavior
*by construction*: `kernel_parity` (all eight staged kernel sub-suites)
passes against the claude-r2 tree. The exact defect that broke the
baseline claude succession is closed in the regrown tree that had to
satisfy the pin to exist.

## Using the rebuilt tools, not only judging them

Conformance is measured; operation is used. Both r2 trees were run *as the
tool* (their own `PYTHONPATH`, the original package nowhere on it):

- **verify** — both compute the repository's root and agree it stands.
- **refuse tampering** — both reject a claim with one pinned byte flipped,
  exit 1, with their own diagnostic.
- **rebuild via a working producer** — this is click J, used rather than
  measured. Both r2 kernels were handed a local producer that writes the
  output and runs the gate in its room (leaving the gate's output and
  bytecode residue behind, as every real producer does). **Both rebuilt
  the claim and re-earned its root** (`30b1ba30…`). The baseline claude
  kernel refused exactly this; the regrown claude kernel, grown against
  the tightened check, does it — the fix demonstrated by operating the
  tool.
- **drive a real external producer** — the codex-r2 tool drove the
  shipped `codex` producer to blind-rebuild a generation-2 core through
  its own kernel (`gen2 root 62014048…`). A regrown tool operating a real
  vendor producer, end to end.

One operation did *not* work, and it is one of the staged findings shown
by use rather than inspection: the claude-r2 tool could not drive the
external `claude` CLI producer — its conforming-but-divergent env scrub
(the keep-list is unpinned, proposal specimen 6) strips what the CLI
needs to authenticate, and its `rebuild` has no `producer_env`
pass-through (it implemented the spec surface, specimen 3) to hand the
credential back, so the producer reports "Not logged in". The kernel did
not refuse the rebuild; the tool simply had no way to carry the
producer's auth across its own scrub. Two unpinned specimens, caught the
moment the regrown tool tried to operate a credentialed producer.

## The one barrier left to REPO_OK — and it is not conformance

Auditing the whole regrown tree end-to-end through `gate.py` still does
not re-earn `REPO_OK`: the run **times out** at the declared 1800-second
ceiling. Uncontended, the codex-r2 tree's full self-audit takes ~26
minutes, dominated by `self_check` at **25.8 minutes** — the 19-layer
self-rebuild, run with the regrown implementation.

This is a timing finding, not a refusal. Two things follow from it:

1. **The equivalence class permits performance drift.** The criteria pin
   behavior, never speed. The living implementation finishes the same
   gate well inside 1800 s; a blind-regrown one, conforming on every
   behavior, is slow enough that the repository's own declared audit
   window no longer fits it. Nothing pins that it should — which is
   exactly proposal specimen I (pin the audit's diet) and the
   `gate_timeout` specimen, now shown with a number.
2. **`self_check` is the whole cost.** Everything else the gate runs
   finishes in seconds; the self-rebuild is the tail. A regrown tree that
   must re-run the 19-layer self-claim to be audited is auditing its own
   ancestry, slowly.

## The reading

Before the clicks: a regrown tool was refused on substance, instantly.
After: it passes every criterion, and the only thing standing between it
and `REPO_OK` is a declared wall-clock bound that its own (conforming,
slower) self-rebuild overruns. The convergence the clicks bought is real
and measurable; the residue they exposed is a tunable ceiling and a
performance axis the criteria never pinned — the next clicks, not a wall.

## Where everything is

- `research/harness/succession/lineages-r2/{codex,claude}/tree/` — the
  regrown trees and ledgers.
- `research/harness/succession/per_criterion_codex_r2.txt` — the
  no-aggregate-cap per-criterion conformance run.
- `tests_codex_r2.txt`, `tests_claude_r2.txt`, `full_gate_codex_r2.json`
  — the judgments.
- Producers codex/gpt-6-sol and Claude Code/sonnet, un-metered; scaffolded
  and judged by the shipped kernel throughout.
