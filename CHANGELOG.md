# Changelog

All notable changes to this project are documented here. This project's
*claims* are versioned by content hash rather than by release number; when a
claim's identity moves, the entry says so and names both roots.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
  is kept, proven and verifying, at `conformance/kernel-2.0/`; the proof did
  not transfer and was re-earned against the revised suite.
- Repository layout now follows Python conventions: `src/`, `tests/`, `docs/`,
  `scripts/`, plus `conformance/` for the identity-bearing suites and claims.
  No claim identity changed — declared paths are claim-relative.

### Fixed
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
