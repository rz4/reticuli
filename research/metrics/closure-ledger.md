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
| — | 2026-10-06 | e2b77b87 | codex (r5) | REFUSED (self_check: warm-ritual order) | PASSED — first ever (trial_codex_r5.json; gen2 root 6a2e6c14) | yes | no | NOT QUALIFYING |
| — | 2026-10-06 | 5eabb96e | codex (r6) | REFUSED (lockfile: format-1 guidance drift, chain-wide) | FAILED (producer HOME scrubbed; 401 at the API) | yes | no | NOT QUALIFYING |

Count toward k=3: **0**. r5's three seams were signed and landed
(recipe-first bundle) and r6 confirmed all three closed while
surfacing three more (format-1 supplied-step guidance → the chain
migration proposal; the producer's HOME; kill-tree promptness) — six
generations, six-for-six on close-and-find. Family-2 budget still held
for a post-signature boundary.

| — | 2026-10-06 | c6eac133 | codex (r7) | REFUSED (timeout 1800.019 s — the envelope; every reached criterion passed; latent: step-order drift, 13/20 roots) | PASSED (trial_codex_r7.json; bootstrap SUCCESSION HOLDS, first ever) | NO — the refusal IS the envelope | no | NOT QUALIFYING |

Count toward k=3: **0**. r7 is the first generation with ZERO new
behavioral seams — the walls left are enumerated: the gate window (a
calibration decision, staged: raise-the-gate-window) and the step-order
form-member (closable as a class, staged:
format-4-canonical-step-order). The distance to closure is now a list,
not an estimate.

Non-qualifying runs, kept for the record:

| run | root | why it does not count |
|-----|------|----------------------|
| r1–r3 | 16297fb0…51635f09 | earlier roots; boundary changed after each |
| r4 | 3e7dc827/79bce6fb | refused by the identity gate (audit_deep depth); produced three adopted counterexamples — the run that taught the bar its condition 4. Negative control for the trial instrument: `trial_codex_r4.json` (fails at rebuild on the jailed producer, as designed). |
