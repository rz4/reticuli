# The closure ledger — counting to k = 3

*The reticuli→reticuli arm closes at three consecutive qualifying
blind reconstructions (docs/transitions.md, keyholder-signed
2026-10-05). This ledger is the count. An ADOPTED counterexample —
a signed boundary change — resets it to zero; discoveries that are
staged but unsigned do not.*

Qualifying = frozen root + independent producer + distinct
implementation + full conformance gate + the recursive step through
the trial tool's own CLI (`research/harness/closure/trial.py`) +
within envelope. Across the three: ≥2 model families, ≥1 re-earned
outside the generation environment.

| # | date | root | family | gate | recursive step | envelope | outside | verdict |
|---|------|------|--------|------|----------------|----------|---------|---------|
| — | 2026-10-05 | e2b77b87 | codex (r5) | pending | pending | pending | no | IN PROGRESS |

Count toward k=3: **0**.

Non-qualifying runs, kept for the record:

| run | root | why it does not count |
|-----|------|----------------------|
| r1–r3 | 16297fb0…51635f09 | earlier roots; boundary changed after each |
| r4 | 3e7dc827/79bce6fb | refused by the identity gate (audit_deep depth); produced three adopted counterexamples — the run that taught the bar its condition 4. Negative control for the trial instrument: `trial_codex_r4.json` (fails at rebuild on the jailed producer, as designed). |
