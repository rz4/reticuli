# Evidence map

Every quantitative claim the manuscript makes, mapped to the repository
artifact that supports it. Compiled by audit of the repository at commit
`1ae44f0c564e618681267262a4928f149d955a09`, self-claim root
`900b6594d4ade4d51f1331054437fa311f5f7a73153a722781d4fb701192cc0f`.

Each row carries a **status**:

- `measured` — the number is produced by a script in the repository from
  data in the repository, and was re-read during this audit.
- `recorded` — the number appears in a dated project record written at
  the time of the run, and the underlying raw data is present.
- `author-reported` — stated in a project document; the raw data is not
  separately recoverable.
- `laboratory-only` — measured, but entirely on hardware and under an
  operator the authors control.
- `GAP` — the manuscript needs this and the repository does not supply
  it. Must be resolved or the claim cut before submission.

No row is `independently repeated`. See §6.

---

## 1. The protocol (manuscript §3)

| claim | artifact | status |
|---|---|---|
| M1/M2/M3 are normatively defined, with M3 as independent rebuild from pinned inputs only | `spec/verification.md` §"Crosscheck: the three-machine test" | recorded |
| Acceptance is three-valued: accept / reject / incomplete, and incomplete can never accept | `spec/verification.md` §"The verdict is three-valued" | recorded |
| Hard conditions: one root, byte reuse, every verdict re-earned, cost band, claim-declared conditions | same | recorded |
| Cost envelope compares M3 to M1 in the strongest shared unit (`usd` > `tokens` > `calls` > `seconds`), tolerance default 2.0, settable in [1.5, 4.0) | same | recorded |
| Producer independence is **recorded, never enforced**; same-vendor rebuilds marked `independence unestablished` | same | recorded |
| `verify` is identity only; `audit` is the only verb that re-earns a verdict | `spec/verification.md` verb table | recorded |

**Writing constraint.** The manuscript must not claim the protocol
establishes producer independence. The specification itself states that
content cannot prove blindness. This is the single most important
honesty constraint in the paper.

## 2. Identity (manuscript §4)

| claim | artifact | status |
|---|---|---|
| Root is computed over canonicalized identity-bearing material, excluding generated implementation bytes | `spec/identity.md`; `src/reticuli/_kernel/identity.py` (skips `class == "generated"`) | measured |
| Format 3 strips producer guidance from the preimage | `_preimage_recipe` in `_kernel/identity.py`; `spec/identity.md` | recorded |
| Format 4 canonicalizes step order at seal, making the step list a set | genome map row "format 4"; `spec/identity.md` | recorded |
| Identity vectors: 17 pinned test vectors | `spec/vectors/` | measured |
| A specification change produces a new root; lineage is retained | `docs/transitions.md`; `research/provenance/revision-*.md` (34 records) | recorded |

## 3. Self-hosting (manuscript §7.1, §7.2)

### 3.1 The qualifying trials at the final boundary

Boundary root `900b6594`. Sealed trial claims, each a claim whose own
gate re-earns the verdict:

| trial | sealed claim root | producer | status |
|---|---|---|---|
| 1 (r23) | `61d77f1f5d442908…` | codex, gpt-6-sol | measured (manifest read this audit) |
| 2 (r24) | `29b185a8482cecc3…` | claude, sonnet | measured |
| 3 (g2) | `2568e7d4224de859…` | codex-authored, r24-orchestrated | measured |

Source: `research/harness/closure/trialclaims/{r23-codex,r24-claude,g2-codex}/.reticuli/manifest.json`.
Ledger narrative: `research/metrics/closure-ledger.md`.

**The grandchild (trial 3) is the load-bearing result for RQ2.** Every
layer was authored blind by one family while every kernel act — sealing,
jailing, rebuilding, computing roots — was executed by trial 2's regrown
code. Its own recursive step produced a further generation at the same
root: `trial_codex_g2.json` records `child_root` =
`4c2abcbfb3e0ac15f4d897b0e347c884a325f33623cbba811bdd26f8c41e585b` with
`root_equality: "roots agree"`.

### 3.2 Non-qualifiers, which the manuscript must report

The instrument refused to seal non-qualifying trials. Verified this
audit: `trialclaims/r20-codex/` and `trialclaims/r22-claude/` have **no
`.reticuli/manifest.json` and no `TRIAL_OK`**, while all five qualifying
directories have both. This is positive evidence that the trial-claim
construction does not seal failures.

| run | family | outcome | artifact |
|---|---|---|---|
| r4 | codex | refused (deep-audit depth); negative control for the trial instrument | `trial_codex_r4.json` |
| r5–r8 | codex | refused: warm-ritual order, format-1 guidance drift, envelope timeout (1800.019 s), `RETICULI_OUTPUT` unset | `trial_codex_r{5,6,7,8}.json`, ledger |
| r10 | claude | refused 21 s: `pack` does not expand patterns in `inputs` | `trial_claude_r10.json` |
| r12 | claude | refused 0.4 min: room recipe materialized as JSON in `reticuli.toml` | `trial_claude_r12.json` |
| r13 | claude | refused 22 min: deep audit dedups by component name, not root | `trial_claude_r13.json` |
| r14 | claude | grew 21/21 then failed identity: regrown `pack` seals `{component, root}` while its `_audit_deep` reads `link["input"]` | ledger; `full_gate_claude_r14.json` |
| r15 | claude | failed identity 41 s: `audit_deep` resolves components by physical nesting, walks 2 of 18 layers | ledger; `full_gate_claude_r15_detail.json` |
| r16 | claude | **identity PASSED** (24.4 min, 18 layers), held-out 104/104, recursive step passed, bootstrap 5/6 — only `audit_repo` failed | `trial_claude_r16.json`, `bootstrap_claude_r16.json` |
| r18 | codex | failed identity 0.8 min: the r15 flat-resolution seam, now cross-family | ledger |
| r20 | codex | failed identity 21 s: `pack` raises on a glob matching no file | ledger; unsealed trial dir |

### 3.3 The seam-discovery sequence (RQ4's self-hosting evidence)

New seams per generation across the codex hardening arc: **3 (r4), 3
(r5), 3 (r6), 2 (r7), 1 (r8), 0 (r9)**. Source: `closure-ledger.md`,
stated at r7 ("New seams per generation across this arc: 3, 3, 3, 2, 1")
and at r9 ("ZERO new seams; the arc's sequence is 3, 3, 3, 2, 1, 0").
Status: **recorded**, counted by the project at the time.

**GAP.** These counts are narrative, not emitted by a script. Before
submission either (a) derive them mechanically from
`research/provenance/revision-*.md`, or (b) present them as the authors'
classification with the classification rule stated. Do not present as
`measured`.

The claude arc is the counterpart and must be reported with it: seven
consecutive draws (r10, r12, r13, r14, r15, r16, r17), each refused by
one seam, each seam deeper than the last, with three signed repairs
between them, ending in r17 — the first claude qualifier. Source:
ledger; summarized in the genome map's "articulation reading".

### 3.4 Resets

The count was reset to zero **five times** by adopted boundary changes
(ledger: reset #1 2026-10-07 glob+vocabulary; #2 2026-10-07 room recipe;
#3 2026-10-08 pack→audit_deep; #4 2026-10-09 jail plank 7; #5 2026-10-09
batched exchange pins). Reset #5 surrendered the r17 qualifier by the
keyholder's explicit call. The r19 trial was voided by a keyholder ruling
on the strict reading of no-intervening-change, and regrown as r21.

**The manuscript must report these.** A reader who learns the final count
is 3-of-3 without learning it was reset five times has been misled about
the cost of the method.

### 3.5 Implementation diversity

Measured this audit with `research/experiments/three-machine/convergence.py`
over eight realizations (shipped tree + r9/r11/r18 codex + r14–r17
claude), raw text channel:

| quantity | value | status |
|---|---|---|
| cross-family mean pairwise similarity | 0.1233 | measured |
| within-codex | 0.3168 | measured |
| within-claude | 0.2014 | measured |
| modules present in every realization | 37 | measured |
| modules taking a distinct shape in every realization | 32 of 37 | measured |
| modules that converge | 5: `__init__.py`, `__main__.py`, `_cli/__init__.py`, `_kernel/__init__.py`, `cli.py` | measured |
| size bimodality | codex 4,384–4,842 lines; claude 8,381–8,638 | measured |
| shipped tree is the least typical member of its own class | tree score 0.0736 | measured |

These reproduce the project's prior reading (`research/provenance/experiment-2026-10-09-corpus-assays.md`:
within-codex 0.317, within-claude 0.201, cross-family 0.123, 32 of 37) to
within 0.003 on seven of eight tree scores; `r16a` is high by 0.0070.
Full output: `research/experiments/three-machine/validation.json`.

**Note for the manuscript.** A second, normalized channel (comments,
docstrings and layout removed via `ast.unparse`) gives cross-family
0.1978, within-codex 0.3491, within-claude 0.2898. Report both. The raw
channel overstates diversity to the extent that prose differs; the
normalized channel is the one that speaks to implementation structure.

### 3.6 Convergence per locus

The per-module convergence gradient (0.377 at `_kernel/core.py` down to
0.024 at `_cli/dispatch.py`) is in `research/metrics/genome-map.md`,
"expression track", over seven complete regrown trees. Status: recorded.
The claim the project draws from it — that every seam to date occurred
at a low-convergence locus — is **author-reported** and should be
presented as an observation with its seam sites named (`pack.py` 0.117,
`_kernel/run.py` 0.116, `registry.py` 0.060), not as a tested
correlation.

### 3.7 Specification repairs (manuscript Table 3)

`research/metrics/genome-map.md` gene table: 19 adopted obligations, each
with locus, the failure that selected it, the signed fixation, and the
steering evidence since. Full lineage of 34 recorded revisions in
`genome-map.json`. Status: recorded, with signatures.

Rows with explicit post-fixation steering evidence, usable as causal
claims about repair:

- pack→audit_deep round-trip: "steering confirmed 4/4" (r15–r18 authoring
  layer first-attempt).
- jail floor plank 7 (user lookup): "steering confirmed 1/1" — r17 passed
  both the run layer and `audit_repo`, becoming the first claude
  qualifier.
- empty selection: r21's `pack` took the chain's legitimately empty
  early-layer patterns without complaint.

**Mis-pins averted**, which the manuscript should report as the
discipline record: the r13 dedup-key diagnosis (withdrawn after
measurement falsified it), the silent-truncation facet (falsified: r13
raises rather than truncates), the nested-staging localized fixture
(mechanism isolated, fixture unencodable, accepted as caught).

### 3.8 Resource obligations

| claim | artifact | status |
|---|---|---|
| A reconstruction's chain build showed a ×95 doubling ratio against 2.1–3.5 for conforming implementations; a $2^K$ model fit the interpolated point to 1% | genome map row "the chain build is incremental"; `research/harness/corpus/scaling_probe.py`; ledger r22 | recorded |
| A copy procedure duplicated shared ancestors per reaching path, reaching 23 GB for a 20-layer chain | genome map; project disk measurement | author-reported |
| Growth envelope declared on recursion-bearing axes: `audit_deep` and pull doublings ≤ ×8, corpus band 1.1–3.5, no violator | genome map row "the growth envelope"; `research/harness/corpus/growth_battery.py` | recorded |

**GAP.** The 23 GB figure is a disk observation made during development,
not a logged measurement. Either re-measure it with the defective copy
procedure reinstated, or state it as an approximate observation. Do not
give it a decimal.

### 3.9 Held-out testing

`104/104` held-out tests recur across r16, r17, r19, r20, r21, r23, r24
(ledger, `bootstrap_*.json`). The battery is deliberately outside the
root, so it measures drift rather than identity.

**GAP.** The manuscript needs the held-out battery's provenance: when it
was written relative to the trials, by whom, and whether it was ever
revised in response to a trial failure. If it was revised after seeing
failures, it is not held out in the strong sense and must be described
accordingly.

## 4. Consumer substitution (manuscript §7.3)

The cleanest experiment in the repository and the one that most directly
answers RQ3.

| claim | value | artifact | status |
|---|---|---|---|
| Dependency `kvparse` root | `0459778c…` | provenance record | recorded |
| Consumer `portdoubler` root | `4191e4d9…` | same | recorded |
| Tightened dependency `C_1` root | `76b028ab…` | same | recorded |
| Blind reconstructions from `C_0` | 6 (codex gpt-6-luna/sol/astra; claude sonnet/opus/haiku) | same | recorded |
| Pass the dependency's own gate | 6/6 | same | recorded |
| Distinct build digests | 6/6 | same | recorded |
| **Keep the consumer working** | **0/6** | same | recorded |
| Shared cause | all six chose last-wins for duplicate keys and kept values as strings, so `cfg["port"] * 2` became `"80" * 2 = "8080"` | same | recorded |
| From the tightened `C_1` | 6/6 pass and 6/6 keep the consumer working | same | recorded |
| Cost of the repair | two pinned lines | same | recorded |
| Retries | one: gpt-6-luna's first `C_1` session ended without passing; its second converged | same | recorded |

Artifacts: `research/provenance/rebuild-2026-09-28-substitution-stage2.md`,
`research/harness/substitution/` (stage 1, no producers),
`research/harness/substitution/stage2/` (runner, claims, ingested
reconstructions, raw results).

Stage 1, hand-written: three implementations pass `C_0`, only one keeps
the consumer working.

**This experiment carries two findings the manuscript should separate.**
First, gate-passing does not imply substitutability. Second, and more
important for the paper's argument about shared priors: the six failures
were *one shared reading*, not six random ones, so no amount of
cross-checking reconstructions against each other would have surfaced
it. Only the consumer did.

## 5. External software: jq (manuscript §7.4)

### 5.1 Frozen materials and baseline

| claim | value | artifact | status |
|---|---|---|---|
| Corpus | jq-1.8.1 official, 522 parseable cases | `research/external/jq/corpus/` with SHA256SUMS | measured |
| Oracles, outside the specification forever | jq 1.8.1, gojq 0.12.19, jaq 3.1.1 | `oracles/VERSIONS` | recorded |
| Three-way agreement | 332 / 522 | `baseline/run_baseline.py` → `baseline.json`; `PHASE0.md` | measured |
| Three-way disagreement | 149 / 522 = **28.5%** | same | measured |
| Per-tool corpus pass | jq 479, gojq 408, jaq 337 | same | measured |
| Harness artifacts excluded | ~43 cases fail even for reference jq under the plain runner | `PHASE0.md` | recorded |
| `S_0` carve | 465 eval-core cases, root `d275f7f162c9…` | `carve_s0.py`; `jq-ledger.md` | recorded |

The 28.5% figure is the paper's best single piece of external evidence
that officially maintained test corpora do not pin behavior, and it cost
no model spend.

### 5.2 Generation 1 — the extensional collapse

| claim | value | artifact | status |
|---|---|---|---|
| Conformance | 465/465 on `S_0`, root equality, `ret verify` clean, first attempt | `generation-1.md` | recorded |
| The implementation was a lookup table | 465 entries with input normalization and an error for everything else | `evidence/sample1-the-lookup-table.py` | measured (source present) |
| It said so | "The supplied specification is an extensional set of observations… This is not a general jq interpreter." | same | measured |
| Behavior on 1,395 novel seeded probes | agrees with reference jq on 587; errors on 808 | `probe_differential.py`, `probes_g1_sample1.json` | recorded |
| Human implementations on the same probes | split from reference jq on 296 of 1,395 | same | recorded |

**Data-integrity disclosure required.** The generation-1 per-probe JSON
was overwritten by a later run reusing the path. Because probes are
seed-deterministic and the lookup-table source was preserved, the record
was regenerated exactly (587/808/296). The manuscript must disclose this
in the artifact statement. No other number depends on an overwritten
file.

### 5.3 Repairs

| move | root | repair | artifact |
|---|---|---|---|
| `S_0`→`S_1` | `05c83a25a405…` | 16 metamorphic/computed laws over gate-time entropy-seeded inputs, validated on three fresh seeds against reference jq | `jq-ledger.md`, keyholder-signed |
| `S_1`→`S_2` | `05ee9161db52…` | 28 intensional error laws over gate-time generated wrong-typed inputs, each condition verified unanimous across jq/gojq/jaq before writing, validated on five fresh seeds | same, keyholder-signed |

**Three candidate laws were rejected by that validation before being
committed** — `transpose`/`reverse`/`any` vacuity — because jq's refusals
proved value-dependent rather than type-dependent (`reverse 0` returns
`[]`, `reverse 5` raises, because the definition routes through a length
that is zero). They became `ecosystem-findings.md` instead. This is a
methodological result in its own right and belongs in the manuscript:
obligations must be calibrated against the reference before they are
committed, or they refuse conforming implementations.

### 5.4 Scored predictions (preregistered)

Preregistration signed 2026-10-11 before any room opened:
`research/external/jq/preregistration.md`. Scorer: `score_generation.py`.

| prediction | predicted | measured | verdict | artifact |
|---|---|---|---|---|
| P1 recall of the human-divergence surface | ≥ 30% | **17.6%** (60 of 343) | **FALSIFIED** | `generation-2-scored.md` |
| P2 concentration on human-split probes | enrichment | **2.30×** pooled; of 19 probes where both families diverge, **17 (89%)** are probes where a human implementation also disagrees | SUPPORTED | same |
| P3 novel ambiguity, off-shadow, ≥2 samples | > 0 | **0** | not found | same |
| P5 | — | unscoreable at this n | — | ledger |

Supporting detail: H-shadow 343 probes (24.4% base rate); codex samples
M = 79/66/52, pooled 92 distinct, 43 flagged by all three; claude sample
M = 34, on-shadow 26 (76%), agreement with jq 97.6%. Codex-only recall
was 15.0%; adding a whole second producer family moved it to 17.6%.

The refined finding, which is stronger than the original prediction: the
silence two frontier priors can jointly see is substantially narrower
than the silence that demonstrably exists.

### 5.5 Contraction — and the instrument failure that preceded it

This sequence must be reported in full. It is the paper's best evidence
that the measurement design, not the data, decides the conclusion.

1. Generation 3 at unchanged `S_2` appeared to show a 25% aggregate
   contraction (65.7 → 49.5 per-sample divergence). Claim staged.
   (`generation-3-contraction.md`, now marked superseded.)
2. A **preregistered control** at the unchanged boundary returned mean
   63.0 across three fresh samples. Pooled by boundary: `S_1` 65.7±13.5
   vs `S_2` 57.6±12.6, a 0.64-sd difference. **The control refuted the
   claim within the hour and the claim was withdrawn.**
   (`generation-4-control-CORRECTION.md`.)
3. Rebuilt on paired per-probe divergence rates (`rate_metric.py`), the
   effect is real: at n=5/n=5, 10 closed / 36 held / 1 opened, exact
   one-tailed binomial **p = 0.0059**, while the aggregate on the same
   data is 1.38 SE and not significant.
4. At n=7 (`S_1`) vs n=5 (`S_2`): **15 closed / 37 held / 1 opened,
   p = 0.00026**. Re-run during this audit: `closed 15, held 37,
   opened 1`, expected divergences per sample 67.0 → 57.6.
   (`baseline/rate_comparison.json`, regenerated this audit.)
5. Closures are causal and named: `to_entries` 1.00 → 0.00, `indices`
   0.67 → 0.00, both written explicitly into the error laws.

**Same data, two instruments, opposite conclusions.** The aggregate
discards the pairing between a probe before and after; the pairing is
where the signal is.

### 5.6 The negative cross-family result

| claim | value | artifact | status |
|---|---|---|---|
| claude leg, paired `S_1`→`S_2` (n=1 each) | 12 closed / 22 held / 12 opened, sign test **p = 0.58** — no contraction | `cross-family-finding.md` | recorded |
| The explanation, measured | permissiveness is 54% of codex's divergence and 18% of claude's; the `S_2` repair was 28 error laws, aimed at permissiveness | same | recorded |
| Permissiveness fell in both families | codex 35.3 → 27.5; claude 6 → 5 | same | recorded |
| Falsifiable prediction recorded before the test exists | if the pending elections land as `S_3` and a fresh claude sample's value-split count drops while its permissive count stays flat, this account is confirmed | same | recorded |

**The manuscript must report this as a negative result.** The headline
contraction is codex-only and does not replicate in the other family.
The class decomposition explains why, and the explanation is testable,
but the explanation is `n = 1` on the claude side and carries no
statistical weight on its own.

### 5.7 Byproduct findings in the ecosystem

Three undocumented divergences, each reproducible with one command
(`ecosystem-findings.md`):

- `reverse 0` → jq returns `[]`; gojq and jaq raise. jq is the sole
  permissive implementation.
- `range("a")` hangs jaq.
- `. * 1e9` on a string hangs reference jq (non-lazy string repetition).

Two of the three are in the reference implementation. These are
offered as byproducts of the method, not as contributions of the paper.

### 5.8 Open keyholder decision

`elections.md`: the 19 consistently divergent programs reduce to four
classes — A (6, error wording only, no pin by precedent), B (9, jaq the
sole outlier, mechanical consensus pin), **C (3, the genuine election:
`index`/`rindex`/`indices` on an object, where jq returns `null` and both
reimplementers raise)**, D (1, the jq hang, a finding not a pin). Class C
is unresolved at the time of writing and the manuscript should say so.

## 6. What no artifact supports

These must be stated as open in the manuscript, not softened.

1. **No external operator has repeated any judgment.** The two files
   named `outside_reearn_codex_{r11,g2}.json` are *same-host dry runs of
   the condition-5 instrument*, not external replications: the recorded
   host is the same `arm64`/`darwin`/`python 3.14.3` machine, and each
   carries `operator_note: "fill in or sign the record"`. The g2 dry run
   passed (substituted gate ok, 75.2 s); the r11 dry run failed. The
   protocol and signed-receipt format are specified in advance
   (`research/harness/closure/outside.md`,
   `.github/workflows/receipt.yml`, `check_receipt.py`), and nothing has
   been returned. **Every self-hosting result is therefore
   `laboratory-only`.**

2. **Continuous integration is not external replication.** CI
   re-executes the criteria on platform configurations the authors do
   not administer, but it runs the authors' workflow. The manuscript
   must keep this distinction explicit (brief §9).

3. **Blindness is a declared protocol, not an enforced provenance
   wall.** The harness does not route the original to the producer, and
   `spec/verification.md` states that content cannot prove blindness.
   Mitigations are indirect: distinct artifact shapes (§3.5), two
   unrelated producer families, a held-out battery outside the root.
   Supporting documentation: `docs/threat-model.md`.

4. **Specification and probe population co-evolved.** The criteria were
   authored by the method's designer and revised repeatedly in response
   to the behavior of the two producer families used to probe them. This
   is the right way to develop a boundary and a confound when measuring
   one.

5. **jq is heavily represented in producer training data.** Its
   agreement results are therefore uninformative; only its divergences
   are used. `generation-2-scored.md` states this directly ("with
   contamination this heavy, the priors reproduce jq's documented
   semantics well and fail only where jq is silent about errors").

6. **No cost study exists.** The repository records an envelope (`usd =
   40.0` per whole-tool claim, pinned from ledger history) and some
   per-run figures, but there is no comparison against the cost of any
   alternative method. Every economic statement in §8.3 must be framed
   as a hypothesis requiring measurement.

7. **No baseline comparison was run** against differential testing,
   property-based testing, or synthesis tooling as alternative means of
   finding the same defects. Per brief §4, comparative claims must be
   limited rather than invented.

## 7. Numbers re-derived during this audit

Re-run rather than copied, with the command recorded:

| quantity | command | result |
|---|---|---|
| self-claim root | `kernel.seal('.')` | `900b6594d4ade…` |
| convergence readings | `research/experiments/three-machine/convergence.py --validate` | reproduces the prior assay to ±0.003 on 7 of 8 |
| jq paired comparison | `research/external/jq/rate_metric.py` | 15 closed / 37 held / 1 opened |
| trial claim roots | manifests under `trialclaims/*/` | five sealed, two absent (r20, r22) |
| producer wall-clock | ledgers under `lineages-*/*/ledger.jsonl` | codex median 40 min, claude median 186 min, 21 layers |
| retry counts | same | codex 0–1 per run; claude 0–4 |

Producer models recorded in the ledgers: codex `gpt-6-sol` (also
`gpt-6-luna`, `gpt-6-astra` in the substitution experiment), claude
`sonnet` (also `opus`, `haiku` in the substitution experiment).

## 8. Terminology translation

The repository uses a biological register that the manuscript must not
inherit (brief: avoid evolution, domestication, artificial life in the
main technical argument).

| repository term | manuscript term |
|---|---|
| gene, pin | acceptance obligation, pinned requirement |
| genome, pin set | committed requirement set |
| phenotype | implementation |
| selection event, seam | failure witness, underspecification site |
| fixation | signed adoption of a requirement |
| expression, convergence | measured implementation agreement |
| domestication | specification recovery |
| speciation, heredity | (omit) |
| the ratchet | specification refinement loop |
| wild, feral | independently developed, external |
| room | reconstruction workspace |
| claim | specification with its sealed evidence |
