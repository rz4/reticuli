# Changelog

All notable changes to this project are documented here. This project's
*claims* are versioned by content hash rather than by release number; when a
claim's identity moves, the entry says so and names both roots.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
- A kernel applying a sandbox now exports `RETICULI_JAILED`, so a gate that
  itself runs claims inherits the sandbox instead of failing to nest.
- Sandboxed gates get a writable `TMPDIR`/`HOME` inside the claim.
- `cost()` totals wall-clock again, and the cost envelope compares exactly one
  unit — the strongest both machines measured.
- Authoring no longer pins case-folded filenames, which had made the same
  session seal to different roots on case-insensitive filesystems.
