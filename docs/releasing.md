# Releasing

A release is not the source tree tagged; it is an artifact built, published,
downloaded again, and re-earned. This checklist is deliberately boring — the
pattern is GNU Coreutils': test what users receive, not only what you have.

Only a release maintainer publishes (see [`GOVERNANCE.md`](../GOVERNANCE.md)).

## Before the tag

- The release commit is clean and every required CI check is green — including
  the `package` job, which builds the sdist and wheel and installs each into a
  clean environment.
- The version is set through its single source of truth (`pyproject.toml`
  `[project].version`); `ret --version` reads it from the installed metadata,
  so the two cannot disagree — CI asserts it.
- Every interface-changing edit is classified against
  [`compatibility.md`](compatibility.md): human output may change; `--json`
  is stable per release; the record is the durable cross-version contract.
- Every identity-bearing change went through the transition ritual
  ([`transitions.md`](transitions.md)): the repository's own claim verifies and
  freshly audits, each moved root has its `research/provenance/` record, and
  the room (`room/reticuli`) names the current root.
- `CHANGELOG.md` holds the user-facing summary for the release; experiment
  detail stays in `research/`.
- The license state permits the intended distribution. Until then, this repo is
  not published to a public index (see `LICENSE`).

## Build and prove the artifact

- Build both distributions from the release source:
  `python3 -m build` → `dist/*.whl` and `dist/*.tar.gz`.
- `python3 -m twine check dist/*` — metadata is valid.
- Install each, separately, into a fresh virtualenv, and from the **installed**
  artifact (not the checkout) run `ret --version`, `ret --help`,
  `ret verify`, and `ret audit` on a representative example.

## Publish, then distrust yourself

- Tag the release under the chosen signature policy.
- Publish `dist/*` to the approved channel, with hashes and whatever provenance
  the project has adopted (SLSA is the vocabulary to grow into).
- **Download the published artifacts again**, check their hashes, install into a
  clean environment, and smoke-test the entry point. A release is complete only
  when the thing users will fetch has itself been re-earned.
- Point the reusable-verification example at the immutable release tag, not
  `main`.
- Have a documented yank/rollback path ready before you need it.
