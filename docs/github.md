# GitHub and continuous integration

How the standard GitHub machinery maps onto claims. CI here produces
evidence rather than authority, and the authoritative check is the one the
recipient runs.

## What CI runs

On every push, a matrix of operating systems and interpreter versions:

1. Re-verifies the repository root. The root must be identical across
   platforms and interpreters.
2. Runs the full acceptance gate (`criteria/`), not a test subset.
3. Runs the held-out test battery. Tests are outside the root: they change
   confidence, not identity.
4. Audits every shipped example claim cold. A formatter or refactor that
   altered sealed bytes fails here.
5. Writes a record of the machine's results and uploads it as a build
   artifact.

Two further jobs run separately: lint, and package install with entry-point
execution.

Lint excludes sealed material, because pinned bytes are inside an identity
and an auto-formatter that edits a sealed file breaks the claim. The
exclusion list has to be updated when sealed artifacts move, and the symptom
of a stale list is CI failing on bytes no one deliberately changed.

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

In an agent-heavy repository the operational rule is to route agent work to
the generated and unpinned classes, and to route anything touching pinned
material into a queue for human decision. Review any pull request in this
order: did CI re-earn the verdicts, did the root move, and if it moved, was
that intended and signed.

## Transport

Claims travel as ordinary files, whether by clone, archive, or release
asset, and they carry no credibility. To receive one, run `ret verify` for
identity and then `ret audit` to re-earn its promises cold. Publisher and CI
records are comparison evidence rather than substitutes. The mechanics are
in [receiving](receiving.md) and [releasing](releasing.md), and the trust
boundaries are in the [threat model](threat-model.md).
