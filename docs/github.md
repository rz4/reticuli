# GitHub and continuous integration

How the standard GitHub machinery maps onto claims. CI here is evidence
production, not authority; the authoritative check is the one the
recipient runs.

## What CI runs

On every push, a matrix (2 operating systems × 3 Python versions):

1. Re-verifies the repository root. The root must be identical across
   platforms and interpreters.
2. Runs the full acceptance gate (`criteria/`), not a test subset.
3. Runs the held-out test battery. Tests are outside the root: they change
   confidence, not identity.
4. Audits every shipped example claim cold. A formatter or refactor that
   altered sealed bytes fails here.
5. Writes a record of the machine's results and uploads it as a build
   artifact.

Separate jobs: lint; package install and entry-point execution.

Lint excludes sealed material. Pinned bytes are inside an identity; an
auto-formatter that edits a sealed file breaks the claim. The exclusion
list must be updated when sealed artifacts move; this has gone stale twice
here, and the symptom both times was CI failing on bytes no one had
deliberately changed.

## Semantics of a green check

A green run is one more machine's record: the same root re-derived, the
same verdicts re-earned, evidence attached as artifacts. In three-machine
terms, CI plays M2 on every push.

A green check does not substitute for the recipient's own audit. If CI
passes and a local cold audit fails, the claim has an undeclared
dependency on something CI shares with the author's environment; that is a
defect the audit exists to surface.

## Pull-request review {#reviewing-pull-requests-when-agents-write-code}

The root partitions every diff into three classes with different review
procedures:

| Diff touches | Meaning | Review |
|---|---|---|
| pinned material (criteria, spec, vectors, declared inputs) | the root moves; the reconstruction population retires | contract change: explicit human sign-off, small diffs, stated rationale |
| generated material (the implementation) | membership question | did gate, crosscheck, audit pass? The diff itself is secondary; the criteria are what is held to account |
| unpinned material (tests, docs, research) | confidence/context | ordinary review |

Operational rule for agent-heavy repositories: route agent work to the
generated and unpinned classes; route anything touching pinned material
into a queue for human decision. Review order for any PR: did CI re-earn
the verdicts; did the root move; if it moved, was that intended and
signed.

## Transport

Claims travel as ordinary files (clone, archive, release asset) and carry
no credibility. Receiving procedure: `ret verify` (identity), then
`ret audit` (promises, re-earned cold). Publisher and CI records are
comparison evidence, not substitutes. Mechanics:
[receiving](receiving.md), [releasing](releasing.md). Trust boundaries:
[threat model](threat-model.md).
