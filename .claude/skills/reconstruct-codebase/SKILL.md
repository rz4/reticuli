---
name: reconstruct-codebase
description: |
  Apply reticuli to an external codebase: layer it into claims, regrow each
  layer blind from its tests, and turn the divergences into findings, then
  issues, then PRs that the target's maintainers can evaluate without
  knowing reticuli exists. Use when the user wants to measure how much of a
  codebase its tests actually determine, strengthen a test suite against
  evidence rather than instinct, or de-risk a refactor by pinning behaviour
  first. The human stays in the loop at every outward-facing step: they rule
  on each divergence, decide which findings become issues, and send every
  PR themselves.
argument-hint: "[path-to-target-repo]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Grep
  - Glob
---

# Reconstruct a codebase

The method in one sentence: a component's tests are its specification, so
hand them to a producer with the implementation withheld, and whatever the
reconstruction does differently is something the tests do not demand —
usually a missing test, occasionally a real bug, and sometimes latitude
worth keeping.

The deliverable is never the regrown code. It is the hardened boundary
(tests, pinned data, recorded proofs) and a findings ledger that converts
into issues and PRs a maintainer can judge **from their own tools alone**.

Work in a fresh clone, never the user's working copy. Commit locally and
plainly; nothing is pushed anywhere without the user saying so.

## Phase 1 — layer the target into claims

Decompose `src/` bottom-up: leaves first (modules importing only third-party
code), then layers composing on them via `ret pull` + recipe steps with
`from = "<component>"`. One claim per layer, each with:

- the layer's test files as pinned inputs
- a hash-pinned requirements lock (`uv pip compile --generate-hashes`),
  as small as the layer's true import surface — the lock *is* a
  measurement: it documents what the layer actually needs
- the implementation files as generated produce steps

Rules learned the hard way:

- **An eager package `__init__` welds layers together.** If importing one
  module drags in everything, do not declare the package `__init__` in leaf
  claims — an undeclared `__init__.py` makes the package a namespace
  package in the room, and the welding itself is finding #1.
- **Reference data is a pinned INPUT, never a pinned output.** Constants
  the implementation reads (cost tables, lookup maps) belong inside the
  root and inside the producer-must-not-touch set. Declared as outputs,
  a producer can rewrite them and the rebuild silently seals a different
  claim.
- **A claim-local conftest beats the repo's.** Pin only the fixtures the
  layer's tests use; the shared conftest usually imports other layers.
- **Pin a `pytest.ini` in every claim** so pytest's rootdir stays inside
  the room instead of ascending to whatever the host has above it.
- **Resealing a leaf orphans its dependents' component copies.** After any
  leaf reseal, re-pull and reseal bottom-up, in dependency order. Script
  it once per target.
- **Check interpreter floors early.** A locked dependency without wheels
  for the host's Python fails at furnish time; pin the lock's
  `--python-version` to what the target's own lock resolves for.

Seal each claim (`ret pack`), then prove it travels: `ret export` →
`ret import` → `ret audit` on the copy. A local audit can pass a claim
that cannot travel, because the room has files on disk that were never
declared — only the round trip catches under-declaration.

## Phase 2 — measure, regrow, read

For each claim: `ret audit` (strict), `ret assess --mutants N`, then
`ret rebuild` with the available producer and `ret crosscheck --record-proof`.

- **Mutation scores mean something only for leaves.** A composed claim's
  sample lands mostly on component-supplied files its own gate rightly
  does not test. For composed layers, the regrowth ratio over the claim's
  *own* files is the layer-specific measure.
- **Regrowth is a sampling instrument.** The same claim under identical
  conditions can succeed twice and fail once. Never conclude from one run:
  divergences that recur across runs are findings about the boundary;
  divergences that appear once are findings about the producer.
- **Never `--recursive` at depth.** Per-layer success p compounds to p^n
  across n chained layers. Regrow each layer independently with a couple
  of retries, its sealed components supplied.
- **Record which model produced each rebuild.** Set the producer's model
  explicitly so the ledger carries it; "whatever the CLI defaulted to" is
  not an answer you want to reconstruct from session logs later.

Read each regrowth with a surface diff against the original: logical code
lines kept (blanks, comments, docstrings excluded — raw counts flatter the
result), and public names the reconstruction does without, with inheritance
and `__getattr__` delegation folded in so only genuine divergences show.

Classify every divergence into one of five kinds before reacting:

1. **Dropped because nothing asks** — live behaviour no test demands.
   The core finding type; each one is a test to write or a deletion to
   propose.
2. **Dropped because it is for humans** — logging, docstrings, error
   prose. Latitude that *should* exist. Do not pin it; a boundary driven
   toward 100% is a worse suite, not a better one.
3. **Equivalent but different** — a proxy instead of wrappers, inheritance
   instead of duplication. A design freedom; pin it only when the choice
   carries meaning, and say why in the test's docstring.
4. **Domain knowledge simplified away** — long constant tables, refusal
   branches, edge-case handling. Tests rarely reach these; decide whether
   the knowledge should become pinned data or explicit tests.
5. **Substantive divergence that passes** — a different algorithm
   satisfying the same gate. The dangerous kind, and the one that
   justifies the exercise. Verify it minimally (see Phase 4) before
   claiming it.

**The human rules on every divergence**: granted freedom, or hole to pin.
That judgement cannot be automated and should not be rushed — present the
classified list and wait.

## Phase 3 — the findings ledger

Keep one `LOG.md` in the workspace. Each entry: a stable number, a title,
the evidence, and two fields that make the file the source of truth:

- **Kind**: `defect` (needs a code change) · `decision` (the team's call) ·
  `criteria-gap` (the suite failed to demand something; closed by tests) ·
  `measurement` · `methodology`.
- **State**: `open` · `fixed here` (a patch exists in this workspace and
  wants a PR) · `closed`.

Derive the actionable list from the file, never from memory. Never renumber
— entries get referenced from test docstrings and pinned files. Update
statuses when the work moves past them, or the ledger quietly lies.

When criteria are strengthened, **close the loop**: reseal, regrow again,
and record the before/after (mutation score, kept ratio, and whether the
reconstruction now builds the real thing). That re-regrowth is the
demonstration that criteria changed what an independent reconstruction is
*forced* to build — the single most persuasive artifact the method makes.

## Phase 4 — convert findings into evidence maintainers can run

This is the step that lets the work travel to people who have never heard
of reticuli. The tool's findings need the tool; the tool's *arguments* must
not.

For every finding going upstream, build a **minimal falsification**: the
smallest edit to the real code that embodies the divergence, run against
the target's own suite with the target's own command.

- Run it on a **pristine checkout** of the target's main — not your
  workspace, whose extended tests will catch what upstream's do not.
- Keep it minimal. Swapping in a whole regrown file fails for incidental
  reasons (its own helpers, imports); a 5-line semantic mutation isolates
  the claim. "Change the perturbation direction; all N tests pass" is the
  honest form of "a different algorithm passes".
- Expect some falsifications to fail — the suite catches more than the
  regrowth ratio implies. Report what the suite *does* catch alongside
  what it does not; the contrast is what makes the gap credible, and
  overstating is the fastest way to lose the audience.

## Phase 5 — issues and PRs, human in the loop

Branches live on a **fork**, never the shared repo. Issues are few: either
one tracking issue for the programme with a checklist, or standalone issues
only for defects that merit their own thread. PRs go out in small batches,
two or three open at a time.

Issue shape (plain English, no method vocabulary):

1. **What's wrong** — the offending code quoted, with exact file:line
   pointers or permalinks.
2. **Reproduce** — the falsification as a table: edit, meaning, measured
   result. Every row runnable in under a minute with the target's own
   test command.
3. **Why it matters** — in the target team's vocabulary (reproducibility,
   provenance of reported numbers, deployment risk), not the method's.
4. **Fix** — one paragraph, and "PR follows" only when it will.

PR shape:

- Follow the target's PR template and run the target's own make targets;
  quote their output.
- Include the falsification **in both directions**: the edit passes on
  main, fails on the branch. That is what makes a test PR reviewable.
- Pin behaviour **at the layer that owns it** — a test file that spans
  layers belongs to no claim and no reviewer.
- Strip method references from test docstrings; justify each test from
  the code ("nothing exercises k > 1") rather than from the discovery
  ("a reconstruction dropped this").
- Flag the genuine judgement calls for the reviewer instead of deciding
  silently.
- Disclosure: comply with the target's AI-assistance policy exactly;
  leave any "I reviewed this and take responsibility" checkbox for the
  human. Say nothing false about provenance — "found while writing
  end-to-end tests for X" must be literally true. Whether and when to
  introduce reticuli by name is the user's call, not the skill's.

**The human sends everything.** Draft issues and PR bodies to files, show
them, and stop. The user files them, or tells you to.

## What done looks like

Every layer sealed, audited, crosschecked with proofs against current
roots. A ledger whose index says what is open, fixed-here, and closed. A
kept-ratio per layer, re-measured after the criteria rounds, with the
reasons for the residual gap named (usually: human-facing output, granted
design freedoms, and domain data now pinned). And upstream: a short trail
of issues and PRs, each standing on evidence the maintainers ran
themselves.
