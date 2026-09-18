# Governance

Reticuli is a small project. This document names authority so that it is
transferable and reviewable, not to build committees. One person may hold
every role below; today the repository owner does.

## Roles

- **Protocol maintainer** owns claim identity, the normative formats in
  `spec/`, verification and reconstruction semantics, and the compatibility
  guarantees. A change to any of these needs this role's approval.
- **Release maintainer** owns versions, release tags, package publication, and
  verifying the published artifact — not just the source checkout.
- **Security maintainer** receives vulnerability reports (see
  [`SECURITY.md`](SECURITY.md)) and may authorize an embargoed fix.

## How changes are decided

The repository is itself a reticuli claim, so changes come in two kinds:

- **Ordinary changes** — implementation, tests, documentation, tooling. These
  do not move the repository root and go through normal review.
- **Identity-bearing changes** — anything that edits a pinned input (the
  recipe, `spec/`, the acceptance suites) and so moves the root. These follow
  the transition procedure: state why identity must move, reseal, re-earn the
  gate, record the old→new pair in `research/provenance/`, and — for a version
  or an external submission — re-earn a blind rebuild. A signature over a
  moved root is a keyholder's act, never an agent's.

The full procedure — the ritual, the accept bars, and the fixpoint stopping
rule — is [`docs/transitions.md`](docs/transitions.md);
[`CONTRIBUTING.md`](CONTRIBUTING.md) has the contributor setup.
