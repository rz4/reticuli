# Cross-judging

*Research tooling — not normative, not pinned.*

The succession runs tested whether descendants SATISFY the parent's
criteria. This harness tests whether they can DO the parent's job:
judge claims — including refusing deliberately broken ones with the
right verdict — and orchestrate the production of another conforming
descendant. Three tools: the original `src/reticuli`, and the r3
regrown trees of both producer families.

    python3 run_crossjudge.py            # full matrix -> crossjudge_report.json
    python3 run_crossjudge.py --skip-b   # judging matrix only

Phase A: six-claim battery (good, equivalence-class variant, tampered
input, tampered generated output, forged verdict, edited recipe), each
judged by each tool's verify and audit. Phase A2: each tool authors the
same claim; the roots must agree. Phase B: each tool orchestrates a
blind rebuild; each child is audited by the other two tools.

## What the first run found (2026-10-05)

- **Refusal competence holds, cross-family.** All three tools accept
  both good claims and refuse all four broken ones, with verify and
  audit drawing the identity/judgment line in the same place (tampered
  input breaks identity; a forged verdict survives verify and falls to
  audit's re-earning). The descendants can judge.
- **Orchestration competence holds.** All three tools drove a blind
  rebuild to a sealed child at the parent claim's root, and every child
  passed audit under both other tools. The descendants can reproduce.
- **Fresh authoring diverges: three kernels, two names.** `pack` in the
  original writes a default `request = "regenerate … to pass the gate"`
  guidance line; both descendants omit it — independently agreeing with
  each other against their parent, because no criterion pins guidance
  text (by doctrine, guidance cannot reject a realization). At format 1
  guidance is identity, so the same authored content mints different
  roots. Staged proposal: `research/proposals/author-at-format-3.md`.
- **The sandbox signal is unpinned.** The original's rebuild result
  reports `quarantine: seatbelt`; both descendants report nothing. The
  jail a verdict was earned in is evidence, and today no criterion makes
  a kernel say it. Staged proposal:
  `research/proposals/pin-the-sandbox-signal.md`.
- **Era-faithful vocabulary drift, as predicted.** The r3 trees predate
  the verdict-vocabulary pin and say `earned`/`error` where the pinned
  vocabulary says `failed`/`broken` — predictions_r4.md (P1) expects the
  r4 generation to close this. The `--json` report schema around the
  word is itself an unpinned seam.
- **CLI flag spellings are unpinned.** `-C` and `--into` exist only in
  the original (codex spells the rebuild target `-o`). The criteria pin
  verbs and handler callables, not flags; the harness drives the library
  surface instead. Whether flags should be pinned or declared free is an
  open contract decision.
