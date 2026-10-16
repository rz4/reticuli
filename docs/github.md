# GitHub and continuous integration

A repository hosting reticuli claims uses the familiar GitHub machinery —
branches, pull requests, checks — but the meaning of each piece shifts,
because identity lives in the root rather than in the tree. This page says
what the CI here actually does, what a green check does and does not
establish, and how to review pull requests when part of the diff is
machine-generated.

## What CI does in this repository

On every push, a matrix of machines (two operating systems, three Python
versions) independently:

1. **Re-verifies the repository's own root** — the checkout must still be
   the claim it says it is, and the root must come out identical across
   interpreters and platforms.
2. **Re-runs the criteria** — the full acceptance gate, not a test subset.
3. **Runs the held-out test battery** — tests are deliberately *outside*
   the root: they change confidence, not identity.
4. **Re-earns every example claim** — the shipped examples are audited
   cold, so a formatter or refactor that silently altered sealed bytes is
   caught here as a failed audit rather than discovered by a user.
5. **Writes and uploads records** — each machine freezes its results into
   the interchange format and attaches them as build artifacts, so a run
   leaves evidence, not just a green dot.

A separate job lints and a separate job installs the package and exercises
its entry point. Lint deliberately excludes sealed material: a claim's
pinned bytes are inside its identity, and an auto-formatter that "cleans
up" a sealed file breaks the claim. If you adopt one idea from this page,
adopt that exclusion — and expect it to go stale every time a sealed
artifact moves, so write the exclusion list where the next person will
trip over it.

## What a green check means

CI here is a **second machine's testimony, not an authority**. A green run
establishes that one more environment re-derived the same root and
re-earned the same verdicts, and its uploaded records make that testimony
inspectable. It does not replace the cold audit a recipient runs
themselves, and it cannot: the entire design assumes verification by
parties who trust no one's green dot, including ours.

This ordering matters in both directions. CI catching a defect is the
system working cheaply; CI passing while a local cold audit fails would
mean an undeclared dependency on something CI happens to share with the
author's machine — which is exactly the class of defect audits exist to
surface.

## Reviewing pull requests when agents write code

The root divides every diff into three kinds, and they deserve three
different reviews:

- **Changes to pinned material** — criteria, specification, vectors, the
  recipe's declared inputs. These move the root: they change what the
  software *is*, retire the standing population of verified
  reconstructions, and require explicit human sign-off. Review these the
  way you would review a contract change, because that is what they are.
  They should be rare, small, and argued for in the change description.
- **Changes to generated material** — the implementation. The only
  question is whether the gate, crosscheck, and audit still pass; the diff
  itself is of secondary interest, because the implementation is
  replaceable by construction. This is where agent-authored code lands,
  and it is why agent-authored code is reviewable at all: the reviewer
  holds the criteria, not the candidate, to account.
- **Changes to unpinned material** — tests, documentation, research notes,
  harnesses. Ordinary code review applies. These change confidence and
  context, never identity.

A practical corollary for agent-heavy repositories: direct agents'
ambition toward the generated and unpinned kinds, and route anything that
would touch pinned material into a queue for human decision. The pull
request then reviews itself in layers — did CI re-earn the verdicts, did
the root move, and if it moved, did a person mean it to.

## Receiving and publishing claims

A claim travels as ordinary files — clone, archive, or release asset — and
arrives with no credibility beyond what the recipient re-earns. The
receiving workflow is `ret verify` (cheap: is this the claim it names?)
then `ret audit` (the real question: do its criteria still pass, cold,
from declared inputs only?). Records produced by the publisher, or by CI,
are evidence to compare against, never a substitute. The guides on
[receiving](receiving.md) and [releasing](releasing.md) cover the
mechanics; the [threat model](threat-model.md) states precisely who is
trusted with what, which for a document of that kind is mostly a list of
who is not.
