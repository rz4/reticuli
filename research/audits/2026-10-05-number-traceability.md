# Audit — every reported number, traced to a recorded input

*2026-10-05, keyholder-directed ("bring the research claims up to the
same standard"). The standard: a number a record reports must
regenerate from evidence in the repository — an instrument plus its
saved inputs — or the record must say it cannot. This pass covers the
instrument-era records (Oct 2–5) and the succession/ladder claims the
write-up leans on.*

## Corrected

- **Trust thermodynamics** (`experiment-2026-10-04-trust-thermodynamics.md`):
  the headline ratios were unit-mixed (per-chain / per-layer) and the
  "transfer" timed was the no-crypto self lookup. Instrument rewritten
  to measure the signed path as itself and emit every number to
  `research/harness/scaling/thermo_report.json`; record corrected in
  place with a visible note; the discovery ledger's cycle-15 row
  corrected to match (≈307× / ≈142× / ≈44,000× per chain).
- **Succession r3's contraction rows** (`rebuild-2026-10-03-succession-r3.md`):
  the head-to-head class numbers (745/248 vs 685/255) were produced by
  editing the instrument's implementation dict by hand — irreproducible
  as published. `surface_silence.py` gained `--only` so the classes
  regenerate by name; both maps are now saved
  (`map_class_r2.json`, `map_class_r3.json`); the record gained a
  traceability note. Reproducing them also caught a real bug: when the
  reference layer joined the chain, the instrument began counting
  reference.py twice (a manual append predating the layer, plus the
  chain's own entry) — every current-era map silently inflated by its
  surface. Fixed; the divergent totals reproduce exactly, and tier 1
  differs by exactly the one consumer the final bundle's pins added
  after the record was written (248→249, 255→256 under today's
  boundary).

## Verified traceable, no change needed

- **Verdict cache 16.6 s cold → 0 s warm**
  (`experiment-2026-10-02-verdict-cache.md`): in
  `research/harness/scaling/cold_run.log` and `cache_store.json`.
- **Tier-1 triage 197 + 67 + 4 = 268**
  (`experiment-2026-10-03-tier1-triage.md`): the per-item verdicts are
  `research/harness/silence/triage_tier1.json` (268 entries).
- **Five-implementation surface map 987 divergent / 262 tier-1**
  (`experiment-2026-10-03-layer-surface-silence.md`):
  `research/harness/silence/map_layers.json`. Generated before the
  double-count bug existed (single reference entry then), so its counts
  stand; the next regeneration under the fixed instrument supersedes it.
- **Held-out tests 102/102 per lineage** (succession records): verbatim
  pytest output in `research/harness/succession/tests_*.txt`.
- **Ladder 8/8 probes × 16 generations** (generation-ladder record):
  `research/harness/ladder/fingerprints.json` plus the per-generation
  trees under `chains/`.
- **Cross-judging matrix** (`experiment-2026-10-05-cross-judging.md`):
  written against `research/harness/crossjudge/crossjudge_report.json`
  from the start.

## Known approximations, labeled as such

- Succession r2's "~26-minute self-audit" and the lineage wall-times:
  ledger timestamp deltas (`lineages*/*/ledger.jsonl`) — reproducible,
  but the records round them, and say so.
- The attested-cache "fresh-host 0.1 s" (cycle 9): measured in a
  scratch run not kept; the corrected thermo instrument now measures
  the same path per chain (0.18 s signed), which supersedes it.

## The rule going forward

An instrument that prints a number the write-up will quote also writes
it to a JSON beside itself, and the record cites that file. Editing an
instrument's constants by hand to produce a comparison is how the one
irreproducible row in this audit happened; parameters exist now — use
them.
