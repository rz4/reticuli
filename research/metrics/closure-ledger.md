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

| — | 2026-10-09 | 2d102714 | claude (r15) | NON-QUALIFIER — grew all 21 layers and CLEARED the authoring layer (the r14 pin steered: record round-trip gone), then failed identity at self_check: regrown `audit_deep` resolves components by physical nesting and returns `unresolved` on the FLAT-staged chain (walks 2 of 18 layers, ok=False in 41s) | n/a | n/a | no | sixth claude seam; staged pin-deep-audit-flat-store-resolution |

r15 is the sharpest claude result yet: the first pin WORKED (authoring
grew; the pack→audit_deep record seam is gone), and the draw advanced to
the next contract one membrane deeper — `audit_deep`'s component
RESOLUTION. r15's walks the chain by physical recursion (component-of-
component under each parent's `sealed/`); the self-claim chain stages its
components FLAT in a shared store resolved by root, so r15 finds
cli-verbs, fails to find cli-parser nested beneath it, and refuses.
SHIPPED audit_deep walks the same flat chain fully (18 layers, ok=True) —
it resolves by root, nested or flat alike. The MIRROR of r13: same
nested/flat staging axis, opposite half (r13 = flat-fixture-missed-
nested materialization; r15 = nested-fixture-missed-flat resolution).
Caught by self_check at the whole-repo level, as r13 was. Sixth
consecutive claude seam, each the unexercised half of a symmetric
contract, and — notably for the finite-vs-generative reservoir question
— each pin so far has advanced the draw exactly one contract deeper and
revealed the next. Staged: pin-deep-audit-flat-store-resolution (root
move; keyholder's call, with the r13 accept-as-caught precedent in
view). Full detail captured: full_gate_claude_r15_detail.json.

| — | 2026-10-09 | 2d102714 | claude (r16) | NON-QUALIFIER by ONE condition, but IDENTITY PASSED — a claude FIRST. Full gate ok=True (24.4 min, all 18 layers re-earned); r15's flat-resolution seam did NOT recur (draw-specific). Held-out tests 104/104. Recursive step (trial.py) PASSED (export/import/rebuild/root-equality/parent-verifies-child). Bootstrap 5/6 (version, verify_repo, verify_intact, refuse_tampered, gen2_core_rebuild) — ONLY audit_repo FAILED: the regrown tool as AUDITOR runs the repo gate under its own run.py sandbox and REPO_OK fails | 104/104 | PASS (trial_claude_r16.json) | no | seventh seam, the FIRST in the auditor role; staged pin-sandbox-permits-a-real-gate |

r16 is the arc's turning point. For the first time the claude family
cleared IDENTITY — the implementation-as-content re-earns the root under
full substitution — answering yes to the question six prior draws left
open (can the foreign family PRODUCE conforming software). The sole
remaining gap is in the tool AS AUDITOR: r16's run.py seatbelt profile is
`(deny default)` with a minimal allowlist (file-read/write, fork/exec,
sysctl-read) — enough for the printf gates the run layer's own probe and
every layer gate run, too strict for the repository's COMPLEX gate
(gate.py → self_check rebuilds the whole chain in subprocesses, needing
mach-lookup etc.). Shipped is `(allow default)(deny network*)(deny
file-write*)`, which denies the forbidden and permits a real gate.
Surgically confirmed: flipping ONLY r16's _seatbelt_profile to the
allow-default form makes `ret audit .` pass (rc 1 → 0); control, shipped
audits the repo cleanly in the same environment. The unexercised half:
the run criterion verifies the sandbox DENIES correctly, never that it
ALLOWS enough for a real gate; and --full-gate missed it because that
runs r16 as CONTENT under the SHIPPED sandbox, never r16's own run.py.
Seventh consecutive claude seam, every one the unexercised half of a
symmetric contract, every one at the digital/material membrane — the
sixth were all in the producer-as-content; the seventh is the first in
the tool-as-auditor, a surface earlier draws never reached because they
failed as content first. The recursive step (trial.py) PASSED — it
exercises rebuild + verify (identity by hash), never the complex
sandboxed audit, so it never touches the seam. r16 therefore fails
EXACTLY ONE scored condition (audit_repo) and passes every other it
reached: a single sandbox-policy line from the first claude
qualification. Full detail: full_gate_claude_r16_detail.json, bootstrap_claude_r16.json.

**LANDED 2026-10-09 (root 2d102714 -> 71fd7559, commit 2783df3; room
96879d8):** pin-sandbox-permits-a-real-gate, signed. Encoded as a seventh
plank on run_check's jail floor — a gate may look up the user it runs as
(pwd.getpwuid -> opendirectoryd via mach-lookup). The RUN layer root
moved alone (687b376b -> 7d78f6b3). Verified before landing: the macOS
sandbox log named the denial; the plank returns status failed under
r16's run.py and ok under shipped; flipping only r16's profile to
allow-default fixes its audit; new root re-earns cold gate + deep audit,
ret verify clean. **By the ratchet rule this resets the count to 0** —
r16 was a non-qualifier so no qualified trial is lost, but the boundary
moved, so any future count starts here. Second steering pin for the
foreign family. The floor is now seven planks; each was found by the
next stricter draw, and the sixth (uname) and seventh (user-lookup) both
came from claude draws maturing deep enough to reach them.

Count toward k=3: **0** — boundary now root **71fd7559**. The next draw
(either family) starts the set. A claude draw now inherits the signal
that its jail must permit a real gate: r16 failed only audit_repo and
passed every other condition, so a draw writing a sufficient jail should
be the first claude qualifier.

| **1** | 2026-10-09 | 71fd7559 | claude (r17) | **PASSED** — identity full gate ok=True 25.3 min (all 18 layers re-earned); ret verify; ret crosscheck via r17's own CLI satisfied (M1/M2/M3 all audited at 71fd7559) | **PASSED** (trial_claude_r17.json; bootstrap SUCCESSION HOLDS 6/6 incl gen2_core_rebuild AND audit_repo; held-out tests 104/104) | claude spends the Anthropic plan (not metered USD) | no — first of the set | **QUALIFYING — TRIAL 1 OF 3, AND THE FIRST CLAUDE QUALIFIER** |

**The binding constraint of the whole arc is answered: the claude
family CAN qualify.** r17 is the first foreign-family trial to clear
every in-run condition — the same standard r9/r11 (codex) met, all seven
save #5 (the outside-machine re-earn, a keyholder arrangement). It took
the run-layer crux cleanly (the sandbox pin steered a sufficient jail),
passed identity as content (as r16 first showed), and — the condition
r16 missed — passed audit_repo as auditor, because its run.py jail now
permits a real gate. The seven-draw claude arc: r10 (input globs), r12
(room recipe form), r13 (nested staging, accepted), r14 (pack record
round-trip, pinned), r15 (flat-store resolution, draw-specific), r16
(identity cleared, audit_repo seam, pinned), r17 (QUALIFIES). Three
steering pins drained the reservoir to a qualifying draw. Surface needed
all three retries (draw variance on the heaviest layer, not a seam).

**Count: 1 of 3 at root 71fd7559 — with the binding family banked.** The
two-family bar is now demonstrably reachable. What remains: two more
qualifying trials (codex qualifies near-certainly, so the ≥2-family
requirement is already satisfiable with one more codex pass + one more of
either), condition 5 (outside-machine re-earn, keyholder arrangement),
and no intervening boundary change (a new adopted seam resets to 0).

| — | 2026-10-09 | 71fd7559 | codex (r18) | NOT QUALIFYING — grew 21/21 (both new pins steered: run and authoring cleared on the draw), then failed identity at self_check in 0.8 min: the regrown audit_deep walks 2 of 18 layers and reports cli-parser unresolved on the FLAT-staged chain | n/a | n/a | no | the r15 flat-resolution seam, now CROSS-FAMILY — first codex refusal since r8 |

r18 reclassifies the r15 seam from draw-specific to SYSTEMATIC. codex's
walker is independently written and differently shaped (it copies each
component to a temp room and recurses into the copy; r15 recursed into
the parent's nested store) but makes the same assumption — a component's
own components are reachable from the component's claim — where the real
chain stages all eighteen layers flat in the top claim's shared store,
resolved by root. Byte-for-byte the r15 failure shape (2 of 18 walked,
cli-parser unresolved), reproduced faithfully; control unchanged (the
shipped walker re-earns all 18 on the same chain). Two families, two
independent implementations, one unexercised contract half: the boundary
is genuinely silent about flat-store resolution, and the silence now
costs qualifying trials in both families. The staged
pin-deep-audit-flat-store-resolution carries the cross-family addendum;
landing it is the keyholder's call (a root move; resets the count, which
stands at 1 with r17 banked — adoption would surrender the r17 qualifier
to buy the pin).

Non-qualifying runs, kept for the record:

| run | root | why it does not count |
|-----|------|----------------------|
| r1–r3 | 16297fb0…51635f09 | earlier roots; boundary changed after each |
| r4 | 3e7dc827/79bce6fb | refused by the identity gate (audit_deep depth); produced three adopted counterexamples — the run that taught the bar its condition 4. Negative control for the trial instrument: `trial_codex_r4.json` (fails at rebuild on the jailed producer, as designed). |

Count toward k=3: **0** — RESET 2026-10-09 (fourth time) by adoption of
the batched exchange pins (flat-store resolution + data-dependency
re-earn, root 71fd7559 → c48fbf52; the r17 qualifier surrendered by the
keyholder's explicit call, "pin them"). The data-dependency pin is the
first selected by an INSTRUMENT (the corpus performance assay) rather
than a trial, and it took a registry fix with it — the shipped tool
itself false-passed the witness. Also measured, deliberately not landed:
the closure-travel contract (pull semantics span shallow/compact/
unfolding across the corpus; design decision staged). New boundary: root
**c48fbf52**. The next count runs here and closes with the full
generation-2 (grandchild) growth as the final trial, per the keyholder.

Boundary move 2026-10-09 (third of the day, "the endorsement batch",
root c48fbf52 → 57da3b61): AN ENDORSEMENT COMPOSES (sign re-earns the
composed verdict on claims with components — a deep-broken composed
claim had been signable) and THE CLOSURE TRAVELS WITH A PULL, compactly
(stands-alone + O(1) copies per dependency; the corpus had spanned
shallow/compact/exponential). Count stays **0 of 3**; the set restarts
at **57da3b61**. Four instrument-selected genes fixed in two days with
zero trial spend.
