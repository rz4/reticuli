# The unpinned register — everything still free, and why

*2026-10-04, at the final-bundle root `1361bfd9…`. The keyholder asked
for an audit of what is yet to be pinned. This is the complete register,
from the instruments plus a hand sweep of the axes instruments cannot
see. Every item is classified: DECLARED (free by the spec's own words),
DESIGN (free on purpose, outside the acceptance boundary), ECHO
(apparent residue from trees grown under older boundaries), or OPEN (a
genuine decision still unmade).*

## 1. The instruments, run at this boundary

- **Closure: CLOSED.** `closure_check` passes — every name and keyword a
  pinned file consumes from the generated package is exercised by the
  owning layer's check, across all 37 owned modules.
- **Surface triage: no substantive residue at this boundary.** 270
  consumed divergences across seven implementations: 197 DECLARED (the
  internal seams, freed as a set by `spec/layers.md`), 29 form-only, 38
  alias-form over runtime-converged values, and 6 that look substantive
  but are not — two are the cli-facade attribution artifact (the triage
  resolves the kernel facade, not yet cli's), four are ECHOes: trees
  grown before this week's pins lack `RECORD_NAMESPACE`,
  `rebuild(guidance=, producer_env=)`, pack's full keyword surface, and
  `reuse.layered_audit` — every one now forced by a criterion, so a
  lineage grown under `1361bfd9…` is predicted to show **zero**. That
  prediction is the one outstanding verification (an r4 regrowth; see
  §4).

## 2. DECLARED freedom — the spec's own register, post-bundle status

From `spec/verification.md`'s implementation-defined list, as it stands:

| freedom | status |
|---|---|
| store/ledger/signature filenames | still free (relationships pinned) |
| manifest schema beyond name/root | still free |
| the PASSING gate status spelling | still free (failure classes pinned; `failed` vs `broken` pinned this week; success wording deliberately open) |
| the DEFAULT gate timeout | still free — only the declared value's authority is pinned now (the direction click); an implementation may default low, it may not undercut a declaration |
| cost-envelope tolerance in [1.5, 4.0) | still free |
| `sandbox()` return beyond backend | still free |
| `gate_deciders` beyond the vectors | still free |
| mutation survivor element type | still free |
| `seal()`'s return value | **pinned** (returns this claim's manifest) |
| kernel surface beyond pinned symbols | **resolved** — the closure criterion governs consumption, and `spec/layers.md` declares the rest |
| rebuild resuming into non-empty dirs | still free (both behaviors conforming; the reuse rule annotated, unreachable) |
| the sandbox signal's SENDING half | **still free — the one list entry with teeth left**: the receiving half is pinned (`RETICULI_JAILED` inherited, not nested), the sending half split two real rebuilds, and a kernel silent here dies only when a gate is itself a claim-runner. Candidate pin if nested-gate claims ever matter; deliberate freedom until then. |
| audit-vs-kernel-gate agreement | partially addressed (nested-input fixture in the bundle); the measured judge-dissent on claims whose gates are themselves kernels remains a documented candidate, not pinned |

## 3. DESIGN freedom — outside the boundary on purpose

- **`tests/`** — confidence, not identity; doubles as the held-out drift
  battery, which only works because it is unpinned.
- **`src/` internals** — the equivalence class itself: size, structure,
  naming, internal seams (declared), everything unconsumed.
- **Performance** — behavior is pinned, speed is not, beyond the declared
  `gate_timeout` and cost envelope. A conforming tool may be slow; the
  succession measured one too slow to self-audit in the declared window.
  This is the largest consumer-noticeable freedom left, kept deliberately
  (pinning speed fairly across hosts is the open hard problem; the
  per-claim declarations are the tractable form we took).
- **Diagnostic wording beyond the pinned grammar** — `ret: <verb>:
  <fact>` and the verdict words are pinned; which file a diagnostic
  names, hint phrasing, and prose are free (witnessed variance:
  tamper attribution differed across lineages, harmlessly).
- **`producers/`** — bundled tooling, outside the class: bring your own.
- **README, docs, logo, CI** — the promise, split from the acceptance
  boundary deliberately. NOTE: the recipe's own comment holds a door
  open here — "giving the promise its own separate digest is the held
  v2.4 work." The project's *story* currently has no integrity
  mechanism at all; a meta-claim over docs/ is designed but untaken.

## 4. OPEN — the short list of genuine decisions

1. **`export --blind` ships guidance.** The published room tar carries
   45 producer-guidance strings, while a kernel-furnished rebuild room
   receives the stripped recipe (Fix A). Identity-neutral — guidance is
   outside the root — but the word "blind" overpromises: a stranger
   rebuilding from the room branch gets hints the kernel's own blind
   room withholds, so "regrown from the room" and "regrown blind" are
   currently different experiments. Either strip guidance in
   `export --blind` (a root-neutral src change) or rename/document the
   distinction. A disclosure policy, so the keyholder's call.
2. **The r4 verification.** One regrowth under `1361bfd9…` to confirm
   the predicted-zero substantive residue and watch the bundle's five
   pins steer, as KINDS and pack did. Mechanical; producer-hours.
3. **The sending half of `RETICULI_JAILED`** and **the kernel-gate audit
   dissent** — the two surviving candidates from the spec's freedom
   list (§2). Both documented, neither load-bearing today.
4. **The promise digest (v2.4)** — whether the story gets an integrity
   boundary of its own before strangers start quoting it.
5. **The era caveat** — everything above is certified within one model
   culture; the stranger is the control group. Not pinnable; only
   testable.

## The bottom line

Nothing is unpinned that anything stands on: consumption is closed by
criterion, the internal seams are declared, the historical echoes are
cured in any tree grown under this boundary, and the remaining freedom
is either the spec's own deliberate register or four narrow OPEN items —
one disclosure choice, one verification run, two documented candidates —
plus the one freedom no boundary can close from inside: the culture it
was measured in.

## Update, 2026-10-05

Movement since this register was taken:

- **Item 1 CLOSED.** `export --blind` now ships the guidance-stripped
  preimage recipe at format 3+, matching the kernel's blind room
  (commit 7b74f67). One name, one room.
- **Item 2 IN PROGRESS.** The r4 regrowth is running at `3e7dc827…`
  with predictions stated first
  (`research/harness/succession/predictions_r4.md`).
- **New, from the first cross-judging run**
  (`research/harness/crossjudge/`):
  1. **`pack` writes default guidance into format-1 identity** — three
     kernels mint two names for the same authored content, and the odd
     one out is the original. Staged:
     `research/proposals/author-at-format-3.md`.
  2. **The sandbox signal is implementation-defined** — nothing makes a
     kernel say what jail a verdict was earned in. Staged:
     `research/proposals/pin-the-sandbox-signal.md`.
  3. **CLI flag spellings** (`-C`, `--into`/`-o`) — unpinned; the
     criteria pin verbs and handlers only. Open: pin or declare free.
  4. **The `--json` report schema** — three tools, three shapes around
     the verdict word. Open: pin or declare free.
- **New, from the r4 succession run** (same day, later): the deep
  audit's TRANSITIVE CLOSURE is unpinned — regrown `audit_deep`
  implementations recurse one level where the original walks the whole
  chain, because `exchange_check`'s fixture chain is too shallow to
  force recursion. Caught by `self_check` at the whole-repo level;
  sampled in two independent draws (r3 and r4 trees). Staged:
  `research/proposals/pin-deep-audit-transitivity.md`.
- **New, from the r4 bootstrap** (same day, later still): two more
  sandbox seams, both reproduced and diagnosed. (1) Producer
  confinement is unpinned — the r4 tree jails its producers, which
  kills codex outright and denies the network every model producer
  needs; staged: `research/proposals/free-the-producer.md`. (2) The
  jail's FLOOR is unpinned — the r4 tree's deny-default profile blocks
  `/dev/null`, so true criteria die as false refusals with no detail;
  staged: `research/proposals/pin-the-jail-floor.md`. Together with
  the signed sandbox-signal pin, the sandbox contract now has one
  landed pin and two staged ones.
- **New, from closure trial 1 (r5, 2026-10-06 overnight)**: three more
  seams, each with a witness and a staged pin. (1) The warm ritual's
  ORDER — the r5 pack gates before writing the recipe; the chained
  criteria's verdict guards starve; staged:
  `research/proposals/pin-the-warm-ritual-order.md`. (2) PUBLIC-SURFACE
  fidelity — the r5 kernel wrapper lawfully reimplements rebuild and
  drops the pinned quarantine key; staged:
  `research/proposals/pin-the-public-surface.md`. (3) The jail floor
  lacks a `uname` plank — the r5 jail passes all five pinned probes and
  still crashes criteria that call `platform.machine()`; staged:
  `research/proposals/widen-the-jail-floor.md`. Refined: the
  refusal-diagnostics seam — the r5 audit's API result carries the full
  traceback; only its CLI drops it.
- **New, from closure trial 1 second attempt (r6, 2026-10-06)**: three
  seams, witnesses captured (one by snapshotting a live audit's temp
  rooms). (1) Format-1 supplied-step guidance is identity and
  pack-authored — a conforming pack minted a chain-wide root drift;
  staged: `research/proposals/migrate-the-chain-to-format-3.md`.
  (2) The producer's HOME — the r6 scrub hands producers a scratch
  HOME, severing every credential; staged:
  `research/proposals/the-producer-keeps-its-home.md`. (3) Kill-tree
  promptness — a timed-out gate is refused on the runaway's schedule,
  straddling kernel_check's wall-clock bound (a scheduling-dependent
  criterion); staged:
  `research/proposals/kill-the-whole-tree-promptly.md`. Morsels: pack's
  result count-keys unpinned (selfclaim's reporting consumes them);
  the CLI refusal-diagnostics seam, third sighting.
- **New, from closure trial 1 third attempt (r7, 2026-10-06 evening)**:
  the recipe's STEP ORDER is identity and authoring-order is unpinned —
  two conforming packs order the same steps differently and 13/20 layer
  roots drift (the next member of the authoring-form family after
  wording). Staged: `research/proposals/format-4-canonical-step-order.md`
  (close the class in the preimage). And the ENVELOPE became the
  binding wall: r7 refused by timeout alone at the declared 1800 s with
  every reached criterion passing. Staged:
  `research/proposals/raise-the-gate-window.md`. r7 found ZERO new
  behavioral seams — the first such generation.
- **New, from closure trial 1 fourth attempt (r8, 2026-10-06 night)**:
  the producer is not reliably told WHICH output to write —
  `RETICULI_OUTPUT` is set by one conforming kernel only when a claim
  has exactly one generated output, and relatively rather than
  absolutely, because every pinned producer fixture happens to have a
  single output. Staged: `research/proposals/name-the-next-output-always.md`
  (fourth plank of the producer-environment contract). Also: yesterday's
  kill-promptness bound is too tight under nested load — staged,
  `research/proposals/measure-the-kill-against-the-runaway.md` — and the
  refusal-diagnostics seam is now LOAD-BEARING: a regrown judge's
  refusal could only be diagnosed by snapshotting its room and
  replaying the gate.
- **2026-10-07, r9: nothing new.** The fifth trial found no seam at
  all — the first generation to produce none — and qualified as trial 1
  of 3. The register's remaining items are therefore the live list:
  the refusal-diagnostics seam (a regrown judge's refusal carries no
  human-readable reason; load-bearing in r8, cost a room snapshot to
  diagnose), CLI flag spellings, the `--json` report schema, pack's
  authoring default (staged: author-at-format-4), and the era caveat.
  None blocks the bar.
- **New, from closure trial 2 (r10, the claude lineage, 2026-10-07)**:
  (1) `pack` expands glob PATTERNS in `generated` but nothing pins the
  same for `inputs` — one side of a symmetric parameter pair is
  exercised, and a foreign prior implemented only that side; the chain
  cannot be built without it. Staged:
  `research/proposals/pin-glob-expansion-in-inputs.md`. (2) The verdict
  vocabulary is HALF-pinned: `surface_check` forbids `broken` where
  `failed` belongs and says nothing about the identity-damage case —
  six distinct words across ten conforming implementations, and trial 1
  drew the right one by luck. Staged:
  `research/proposals/pin-the-other-half-of-the-vocabulary.md`.
  (3) CLI flag spellings vary by FAMILY, not by draw: every codex tree
  spells the rebuild target `-o`, the claude tree `--into`. Still
  unpinned, still open.
- **New, 2026-10-07, found while writing the vocabulary pin**:
  PRECEDENCE when a claim is damaged AND a gate fails. The original
  reports `failed` in that case — identity damage is the more
  fundamental fact, and arguably should dominate, but nothing pins
  either way and the pin landed deliberately covers only the clean
  identity-damage case. Open: decide whether `broken` outranks
  `failed`, or declare the combination implementation-defined. (Found
  because the first draft of the vocabulary fixture reused a claim
  that already had a failing gate — the instrument measuring
  precedence when it meant to measure vocabulary.)
- **New, from trial 2 of the new set (r12, claude, 2026-10-07)**: the
  materialized room recipe's SYNTAX is unpinned — at format 3+ the room
  receives the preimage recipe, and a conforming kernel wrote it as
  canonical JSON inside `reticuli.toml`, then refused its own file.
  Self-incompatible at format 3+; invisible because every rebuild
  fixture is format 1 (the copy path). Staged:
  `research/proposals/the-room-recipe-is-toml.md`. Observed beside it,
  undiagnosed: producer invocation CARDINALITY (once per rebuild vs
  once per step) — the bundled producers fail under per-step
  invocation on multi-output claims; decide contract-or-freedom after
  the primary seam is pinned.
- **OPEN, from r13 (2026-10-08), diagnosis NOT yet settled**: r13's
  `audit_deep` is correct on an r13-built chain (18/18) but CRASHED on
  the original-built committed chain (FileNotFoundError on
  `_kernel/__init__.py` during per-layer re-audit staging), while the
  substituted gate failed self_check's layer-COUNT assertion — three
  behaviours on three inputs, not yet reduced to one mechanism. The
  first guess (dedup by name vs root) was FALSIFIED and its proposal
  withdrawn (no duplicate names exist in the chain). The real seam is
  layout/staging-sensitive (nested packages `_kernel/`, `_cli/`); it
  must be isolated by a clean reproduction before any pin. r13's
  verdict (not qualifying) stands regardless; only the fix is deferred.
  ISOLATED 2026-10-08: the reproduced crash is nested component-output
  staging — r13's materialize does a bare copyfile without makedirs, so
  a component supplying reticuli/_kernel/__init__.py crashes (the
  original's _copy_into makes the parent dir). Staged, measured, with a
  traceback: research/proposals/deep-audit-nested-staging-seam.md.
  CORRECTED 2026-10-08: facet 2 (silent truncation) was FALSIFIED —
  r13 raises on a corrupt manifest, it does not silently truncate.
  Facet 1 (nested-staging crash) is confirmed by traceback but could
  NOT be encoded as a clean localized exchange_check fixture — hand-built
  nested chains trip artifacts in both implementations; the faithful
  distinguisher is the self-claim chain, which self_check already runs.
  So the seam is caught at the whole-repo level; the localized pin is
  OPEN (needs a real-chain-faithful fixture). Nothing landed; no root
  moved. See research/proposals/deep-audit-nested-staging-seam.md.
- **(withdrawn) the deep audit's DEDUP KEY is unpinned — the transitivity pin forced a whole-
  chain walk, but a conforming kernel deduped that walk by component
  NAME where the original dedups by ROOT, miscounting the self-claim
  chain's repeated-name ancestors. The three-claim fixture has three
  distinct names, so it cannot tell the two dedup rules apart. Staged:
  `research/proposals/pin-the-deep-audit-dedup-key.md`. Fifth sighting
  of the unexercised-symmetric-half species; the third consecutive
  claude seam, each deeper than the last (21 s / 0.4 min / 22 min).
- **The timing experiment corrected.** The thermodynamics record's
  headline ratios mixed per-chain and per-layer units and priced the
  wrong transfer path; corrected in place with the instrument now
  writing every number to `research/harness/scaling/thermo_report.json`
  (network leverage ~44,000×, not 553,704×).
