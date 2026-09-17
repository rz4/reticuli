# Changelog

All notable changes to this project are documented here. This project's
*claims* are versioned by content hash rather than by release number; when a
claim's identity moves, the entry says so and names both roots.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Records: a signed statement of one machine's results** — the one file
  format other programs may parse. `spec/record.md` pins the document:
  canonical bytes (the identity serialization, verbatim), a closed member
  vocabulary refused in band, per-gate wall-clock deliberately outside the
  signed bytes, and a signature namespace of its own (`reticuli.record`,
  separated from attestation and mint). `reticuli.record` authors them in
  the exchange layer, whose acceptance check now demands emission that
  re-earns its gates, cost relayed with absent-means-unmeasured, and
  tamper-fatal signing. Consuming a record as a crosscheck leg is kernel
  behavior and waits for the v2.2 revision (`scripts/record_check.py`,
  battery F, staged red). The exchange layer gaining a module moved the
  self-claim roots of exchange and every layer above it; the kernel's did
  not move.

### Changed
- **The fault injector is much wider, and now reports its own fault model.**
  It swapped operators and nothing else, which made every mutation score a
  measurement of the injector as much as of the tests: `examples/weak` scored
  0.80 while differing from its sibling implementation only in two constants —
  a fault the injector could not express. It now also injects constants
  (`n±1`, `0`), boolean and membership operators, string results, forced
  branches, dropped return values and transposed call arguments, and the score
  carries `by_kind` and `pool_by_kind` so a reader can see *where* a suite is
  blind. Sampling is stratified across fault kinds, so a small budget over a
  string-heavy program still reaches the constants.

  Widening moved the aggregates very little — `examples/weak` 0.80 → 0.77,
  quirkcalc 0.92 → 0.80, the kernel's own claim 0.50 → 0.57 — because the new
  operators bring easy kills as well as hard survivors. **The breakdown is the
  finding, not the rate**: the kernel claim kills 0 of 5 injected constants,
  and every survivor in `examples/weak` is a boundary.

  Scores from before this change are not comparable with scores after it. Both
  are residue, so no root moves.

### Fixed
- `ret pack` wrote the gate's stdout to **stdout**, where the JSON report
  lives, so `ret pack --json | jq` failed for every claim whose gate prints
  anything — which is all of them, since a check that passes silently is a
  check nobody trusts. The gate's output now goes to stderr, and its *stderr*
  is relayed too: a gate that passed while warning previously passed in
  silence.
- `ret assess` and `ret inspect` accepted no `--json`. Both already emitted
  through the JSON path; they had simply been left off the list, so the
  measurement verb and the recipient's report were the two verbs a script
  could not read.

### Added
- `tests/test_mutation.py` — pins the instrument rather than any score: every
  fault kind stays reachable, docstrings are never mutated (they are equivalent
  mutants by construction), the draw is stratified, and — with a negative
  control — a suite fitted to one value per branch survives the boundary
  mutants while a suite that probes the boundaries kills them.
- `tests/test_streams.py` — stdout carries the report, stderr carries
  everything a person reads. Pinned across `pack`, `verify`, `audit`,
  `inspect` and `assess` with a gate that is loud on both streams.
- `ret inspect` and `docs/receiving.md` — the receiving end. Re-runs the gates
  locally and prints what holds, what it does not establish, and what you are
  trusting; every other verb was written from the author's side.
- `[claim] inputs_manifest` (format 2) — a large input list moves out of the
  recipe into a pinned file. The TOML example's recipe goes from 44 KB to
  1 KB with the corpus still fully committed to. `ret pack --inputs-manifest`.
- `ret audit --reuse` — opt-in local reuse, keyed on claim AND generated
  bytes AND environment, reported as `reused` with the time it was earned.
- `docs/producers.md` and `docs/compatibility.md` — the producer contract
  (environment, cost reporting, the four causes of a failed rebuild) and
  what is stable versus what moves.
- `docs/threat-model.md` — what a claim proves and what it does not, including
  the trust boundaries and the failure modes we hit while building this.
- `examples/weak` — a deliberately weak claim: a model wrote the code and the
  tests together, both look reasonable, and two implementations with different
  behaviour carry the same root. Shows the tool detecting it, and shows what
  the mutation score misses.
- `ret assess` — measures how much a claim's tests actually constrain its code:
  circularity and mutation adequacy by default, re-derivation by a different
  model on request. Descriptive: it reports numbers and names what it did not
  measure, distinguishing "not measured" from "not applicable". `ret pack --by`
  records who produced the original so independence has something to compare.
- `ret assess --heldout FRACTION --heldout-producer NAME=COMMAND` — the
  generalization rung, no longer permanently "not measured". Hides a fraction
  of the claim's case corpus, re-seals on the rest (a different root: fewer
  inputs, the same gate), has each producer regrow the implementation blind
  from the kept cases, and judges every rebuild on the hidden cases one at a
  time. Reports a held-out pass rate per producer and, for two or more, the
  excess agreement `a - (p1·p2 + (1-p1)(1-p2))` — above zero means the
  producers share structure the claim never named. The split is seeded from the
  claim's root, so it reproduces and cannot be shopped for; everything runs on
  copies, so the measured claim is never touched.
- `docs/quickstart.md` — ten minutes, no API key, no model.
- `examples/make` — a claim whose producer is a compiler. Two compiler
  settings produce different binaries carrying the same root; CI asserts both
  halves. **A producer does not have to be a language model**, and used this
  way the toolchain is a build verifier.
- `[claim] format`, an optional version field (absent means 1, so no existing
  claim changed identity). Diagnostic only: a future-format claim already
  fails to verify under an older kernel, but now it refuses in words.
- The toolchain above the kernel: exchange, authoring, agents, launcher and
  the `ret` command line, each with its own acceptance suite.
- `examples/tomli` — a claim over a conforming TOML 1.0.0 parser, judged by
  709 cases from the external toml-test corpus. tomli 2.3.1 and CPython's
  stdlib `tomllib` are members; tomli 2.4.1 is not (it implements TOML 1.1.0).
- `examples/self` — the repository sealed as six layered claims, deep-audited.
- Packaging (`pip install .`, the `ret` entry point) and CI across macOS and
  Linux on CPython 3.11–3.13.

### Changed
- **The kernel claim moved: `d64cc301…` → `4b90feef…`.** The acceptance suite
  now pins seven behaviors that were measured to be under-specified, two of
  which two independently synthesized kernels disagreed about. The predecessor
  is kept, proven and verifying, at `examples/kernel-2.0/`; the proof did
  not transfer and was re-earned against the revised suite.
- Repository layout now follows Python conventions: `src/`, `tests/`, `docs/`,
  `scripts/`, plus `criteria/` for the identity-bearing suites and claims.
  No claim identity changed — declared paths are claim-relative.

### Fixed
- Refusals name what they refused. A malformed recipe now reports the file, a
  gate missing its output reports which step and its command, and `pack`
  failing to match generated files lists the patterns it tried, the directory
  they were relative to, and how many files `--input` already claimed.
- Materializing a generated output preserves its permission bits, so a claim
  whose output is an executable can be audited at all (it previously failed
  with "Permission denied" the moment it was copied to a workspace).
- Acceptance suites write a verdict file only when running as a claim's gate,
  instead of dropping one into whatever directory invoked them.
- A kernel applying a sandbox now exports `RETICULI_JAILED`, so a gate that
  itself runs claims inherits the sandbox instead of failing to nest.
- Sandboxed gates get a writable `TMPDIR`/`HOME` inside the claim.
- `cost()` totals wall-clock again, and the cost envelope compares exactly one
  unit — the strongest both machines measured.
- Authoring no longer pins case-folded filenames, which had made the same
  session seal to different roots on case-insensitive filesystems.
