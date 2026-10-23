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
  leaf reseal, recompose: `ret status <claims-dir>` shows the stale wires,
  `ret pull -C <claims-dir>` (no claim named) repairs them bottom-up with
  warm reseals, never moving a dependent's root. Recorded proofs on the
  refreshed layers predate the new component bytes — the report names
  which; re-earn them.
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
  not an answer you want to reconstruct from session logs later. Check the
  ledger says `model_source: observed` — a producer that chooses its own
  model is the only party that knows which one ran.

### Report a range, never a scalar

A kept-ratio from one draw cannot be compared with a later one, so a
single number gives the loop no gradient: you cannot tell a strengthened
specification from a luckier sample. Take **at least three draws per
layer** at one root, one fresh room each, no retries folded into the
count, and report min/median/max. Measured on a ten-layer ladder: spreads
ran 0 to 7 points per layer, and the volume-weighted aggregate about ±2.
So a few points of movement on one layer is noise; the same movement in
the aggregate is probably signal, and worth a paired re-measure to
confirm.

Five rules that keep such a measurement honest, every one of them learned
by getting it wrong first:

1. **A one-draw layer has no spread, and reports zero.** That zero will
   quietly tighten any aggregate it enters. Treat `n=1` as unmeasured
   variance, not as agreement.
2. **A producer refusal is not a reconstruction failure.** Rate limits and
   exhausted plans say nothing about the criteria. Record them in their own
   bucket and exclude them, or you will report a weak specification where
   there was only an empty wallet.
3. **The failure rate is a second measurement.** A layer that reconstructs
   half the time is telling you something its kept-ratio does not; report
   both, and say that a ratio over survivors is conditioned on success.
4. **Never pool draws across roots.** Different root means different
   criteria, so the difference is the thing you changed, not sampling. Check
   the room's root rather than trusting the directory name.
5. **Never pool draws whose producer is unrecorded.** If pooling needs your
   memory of how you ran them, it is not yet a measurement.

Weight an aggregate by code volume rather than averaging per-layer ratios:
a 40-line layer and a 600-line one are not one vote each.

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

### The kind decides the work

The classification is not filing: it is triage. Each kind maps to a
different work product, a different vehicle, and — the part that sets the
pace — a different answer to *who has to decide anything*.

| kind | upstream work | vehicle | who decides |
|---|---|---|---|
| substantive, and it passes | a test, with a falsification attached | PR | nobody — it is a hole |
| domain knowledge simplified | a test, or pin the data as an input | PR | nobody |
| dropped, nothing asked | a test **or** a deletion | ask first, then PR | the team: is it wanted? |
| equivalent, different | a refactor proposal | issue, discussion | the team: worth it? |
| for humans only | none | — | nobody |

Three consequences worth planning around:

- **Only two kinds need a maintainer's judgment.** Everything else can be
  queued without blocking. That is what makes a long findings list
  tractable; sort by this column before sorting by anything else.
- **Kind 5 is the persuasion budget.** It is the only kind that yields an
  argument a maintainer can run themselves — "here is a seven-line edit
  that passes all 23 of your tests". Those are scarce. Spend them where
  credibility is needed, not on the cheapest fixes.
- **Kind 2 has one trap**: output that looks human-facing but something
  machine-reads. A metrics prefix another tool filters on reads like
  logging and is really kind 1. The question that separates them is "is
  anything parsing this?"

### Count recurrence before filing anything

A divergence in one draw is a finding about the producer; the same
divergence in every draw is a finding about the boundary. Do not eyeball
that — with several draws per layer it is countable, and
"3 of 3 draws dropped it" is the evidence a maintainer actually wants.

Two probes are needed, because they answer different questions:

1. **Public names absent from the reconstruction.** Catches API gaps.
2. **Declared behavioural probes** — a regex per annotated observation.
   The name scan is blind to a dropped side effect, a vanished
   dependency, or an algorithm swapped out, and those are usually the
   findings that matter.

**Validate the probe before trusting the count, because triage converts
instrument error straight into work.** Measured failures, all of which
produced confident nonsense first time:

- A base class inherited from *another module* is not folded by a
  same-file member scan, so every inherited method reads as dropped. One
  layer produced twenty bogus candidates this way.
- A `@property` upstream that became a plain `self.x = ...` in the
  reconstruction reads as dropped unless the scan looks for attributes
  assigned to `self`.
- Walking the whole AST to fix those then reports *local variables* as
  missing API. The walk has to be structured: module and class
  definitions, plus `self` attributes — never function locals.
- An unanchored regex lies. A probe for a `prefix` flag matched an
  unrelated `_flatten_config(prefix='')` and reported the flag as
  surviving; anchoring it to `def log(` reversed the verdict.

And a limit on recurrence as a *ranking*: unanimous does not mean
important. A layer where every draw read config inline instead of caching
it on `self` scores unanimous on several names and is still kind 3 — no
work at all. Recurrence says whether the criteria pin something; the kind
says whether anyone should care.

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
