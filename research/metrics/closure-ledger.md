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

| — | 2026-10-06 | 47ee199b | codex (r8) | **PASSED** — substituted REPO_OK earned, 47.9 min (first ever) | FAILED (RETICULI_OUTPUT unset on multi-output claims) | yes (47.9 of 60 min) | no | NOT QUALIFYING — condition 4 only |

Count toward k=3: **0**. r8 meets six of the bar's seven conditions —
frozen root, independent producer, distinct implementation, **the full
conformance gate**, the envelope, and no intervening change — and fails
only the recursive step, on one seam (staged:
name-the-next-output-always, the fourth plank of the
producer-environment contract). New seams per generation across this
arc: 3 (r4), 3 (r5), 3 (r6), 2 (r7), 1 (r8).

| **1** | 2026-10-07 | d37cd91d | codex (r9) | **PASSED** — substituted REPO_OK earned 44.8 min; ret verify; ret crosscheck through r9's own CLI | **PASSED** (trial_codex_r9.json; bootstrap SUCCESSION HOLDS) | yes (0 metered USD of 40.0; flat-rate path) | no — rides on another trial | **QUALIFYING — TRIAL 1 OF 3** |

Count toward k=3: **1**. Every r9 prediction held and the run found
ZERO new seams; the arc's sequence is 3, 3, 3, 2, 1, 0. Remaining for
closure: trial 2 (the claude lineage — the second family, and the
honest wildcard after four bundles of hardening it has not sampled),
trial 3, and condition 5 — one of the three re-earned on a machine and
operator outside this one, which is a keyholder arrangement rather than
a run.

| — | 2026-10-07 | d37cd91d | **claude (r10)** | REFUSED (21 s — `pack` does not expand patterns in `inputs`; selfclaim's `checks/*.py` reaches the recipe literally) | PASSED (trial_claude_r10.json; bootstrap SUCCESSION HOLDS incl. gen-2 and audit_repo) | yes | no | NOT QUALIFYING — condition 3 |

| **1** | 2026-10-07 | 297827f4 | codex (r11) | **PASSED** — substituted REPO_OK 47.0 min; ret verify; ret crosscheck via r11's own CLI | **PASSED** (trial_codex_r11.json; SUCCESSION HOLDS) | yes (0 metered USD of 40.0) | no — rides on another trial | **QUALIFYING — TRIAL 1 OF 3 (new set)** |

| — | 2026-10-07 | 297827f4 | claude (r12) | REFUSED (0.4 min — the room recipe materialized as JSON in reticuli.toml; self-incompatible at format 3+) | FAILED (same seam; producer-invocation question rides with it) | yes | no | NOT QUALIFYING — conditions 3 and 4 |

Count toward k=3: **0** — RESET 2026-10-07 (second time) by adoption
of the room-recipe pin (root 297827f4 -> a4b19bb1). The third set
begins at a4b19bb1, whose boundary carries both claude draws' lessons
before any counting starts; r13 (claude — the hard family first) is
its trial 1. TRIAL RESULT (2026-10-08): r13 NOT
QUALIFYING — the deep audit dedups by component name where the original
dedups by root, so it miscounts the self-claim chain's repeated-name
layers (staged: pin-the-deep-audit-dedup-key). It did pass the full
bootstrap, gen-2, audit_repo, phase-B orchestration, and the recursive
step — the deepest any claude draw has reached. Three claude draws,
three seams, each the unexercised half of a symmetric contract and each
deeper than the last (21 s, 0.4 min, 22 min). Count: 0 of 3; adopting
the pin resets cleanly (no qualified trial lost in this set). The superseded second set is kept below.

Count toward k=3 (superseded set 2): **1**, of the set begun at root 297827f4 — the first
boundary sampled by BOTH families before counting started, and the
first clean row since the vocabulary pin, so no coin flips hide in it.
Next: trial 2 = the claude lineage at this same root (the symmetric
test of the glob pin), then trial 3 and the outside-machine condition.

Superseded set, kept for the record:

Count toward k=3 (superseded): **0** — RESET 2026-10-07 by adoption of the glob and
vocabulary pins (root d37cd91d -> 297827f4), as the bar requires. The
rows above are the superseded set; r11 begins a fresh set at the new
boundary, the first sampled by both families before counting started.
Trial 2
was the second family's first contact after seven bundles; it found one
load-bearing seam (staged: pin-glob-expansion-in-inputs) and one
unpinned verdict word (staged:
pin-the-other-half-of-the-vocabulary), while still performing the
entire job. Adopting the glob pin resets the count by rule, because
trial 1 qualified against a boundary now known incomplete. The era
caveat is measured: one load-bearing seam in twenty layers for a
foreign prior.

| — | 2026-10-08 | 0482adb5 | claude (r14) | NON-QUALIFIER — grew all 21 layers (a foreign-family first), then refused by the identity deep audit: regrown `_audit_deep` reads `link["input"]` on a lean component record the regrown `pack` sealed with only `{component, root}` | yes (held-out) | n/a | no | deep-audit seam, cleanly pinnable: staged pin-the-pack-audit-deep-roundtrip |

The first r14 attempt (root 7710344f) was INCONCLUSIVE — it halted in
generation at `build` across six attempts. That was NOT layer density
and NOT a claude seam: build_check passed the full claude stack
unsandboxed, and claude's run.py honored the inherited-jail var. The
producer-freedom socket probe (landed with free-the-producer) was
environment-fragile — it asserted absolute network availability where
it meant "the kernel adds no jail," and the succession per-layer gate
runs under an outer confinement that tripped it. Hardened
(harden-the-producer-freedom-probe, root 7710344f → 0482adb5, signed
and landed 2026-10-08); the build layer was NOT split.

Re-run at 0482adb5, r14 then grew all twenty-one layers blind — the
first time the foreign family cleared the whole chain, confirming the
halt had been the instrument, not a claude limit. The assembled tree
FAILED the identity full gate (`ok=False`, 27 min, judge clean to
completion — a merit refusal, not an artifact). The shallow criteria
all pass (`REPO_OK`); the deep recursive audit crashes:
`KeyError: 'input'` in the regrown `_audit_deep`. Mechanism: claude's
regrown `pack` seals component records as `{component, root}` while its
`_audit_deep` reads `link["input"]`/`["output"]` — its own
component-record contract is self-inconsistent. The boundary did not
steer it because `exchange_check` hand-authors RICH records for its
deep-audit fixtures and never builds the composed claim through
`pack(component=…)`; the `pack → audit_deep` round-trip is the
unexercised half of the contract — the same seam species as r10/r12/r13.

This lands the predictions' "deep-audit seam again" branch, but a
DISTINCT and cleanly pinnable mechanism (r13 was a makedirs-less
materialization that resisted a clean fixture; this is a contract
round-trip that encodes in one assertion). Verdict on the two-family
bar: still open. claude has now reached the top of the chain and been
refused by a single, precise, steerable seam — the most tractable
claude failure yet, and the first that warrants a STEERING pin rather
than accept-and-catch.

**LANDED 2026-10-08 (root 0482adb5 → 2d102714, commit 071e2ec):**
`pin-the-pack-audit-deep-roundtrip` was keyholder-signed and landed into
`authoring_check` (pack's own layer — the exchange layer cannot import
pack, which enters one layer above registry/audit_deep). authoring_check
now builds a composed claim via `pack(component=…)` and asserts it
audits deep. The AUTHORING layer root moved alone (9594d8cd → b6bfe31d).
Verified before landing: passes the shipped impl (authoring-ok), bites
the r14 regrown modules (audit_deep raises KeyError 'input'); new root
re-earns the cold gate and deep audit, ret verify clean. **By the
ratchet rule this boundary change RESETS the count to 0** — the r11
codex qualifier (297827f4) no longer counts. First STEERING pin for the
foreign family.

Count toward k=3: **0** — RESET 2026-10-08 (third time) by adoption of
the pack→audit_deep round-trip pin. New boundary: root **2d102714**.

Non-qualifying runs, kept for the record:

| run | root | why it does not count |
|-----|------|----------------------|
| r1–r3 | 16297fb0…51635f09 | earlier roots; boundary changed after each |
| r4 | 3e7dc827/79bce6fb | refused by the identity gate (audit_deep depth); produced three adopted counterexamples — the run that taught the bar its condition 4. Negative control for the trial instrument: `trial_codex_r4.json` (fails at rebuild on the jailed producer, as designed). |
