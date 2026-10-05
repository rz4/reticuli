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
- **The timing experiment corrected.** The thermodynamics record's
  headline ratios mixed per-chain and per-layer units and priced the
  wrong transfer path; corrected in place with the instrument now
  writing every number to `research/harness/scaling/thermo_report.json`
  (network leverage ~44,000×, not 553,704×).
