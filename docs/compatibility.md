# Compatibility

## Status: pre-1.0, and the format has already moved

This is a research tool. The claim format is version 1, and the kernel's own
claim has changed identity twice — once because v2 renamed the recipe keys,
once because the acceptance suite was strengthened to pin seven behaviors it
had left free. Both were deliberate; both are recorded in
[`docs/provenance/`](provenance/bootstrap.md).

**Do not build something on this that cannot tolerate a root changing.** Not
yet.

## The property that makes movement survivable

The recipe text is inside the hash. That has an unusual and useful
consequence: **an incompatible claim cannot be silently misread.** There is no
version-skew failure where an old reader parses a new claim slightly wrong and
proceeds. The root simply does not match, and verification refuses.

So the compatibility story is fail-safe rather than fail-quiet. The worst
outcome of a format change is a claim that will not verify, which is loud, not
a claim that verifies incorrectly, which would be catastrophic.

`[claim] format` improves the diagnosis rather than the safety: a kernel
meeting a format it does not understand says so in words instead of reporting
a bare hash mismatch. Absent means 1.

## What changes what

| change | effect |
|---|---|
| editing any pinned input (a test, a fixture) | **that claim's root moves.** It is a different claim, by design |
| editing a generated output (the implementation) | nothing moves — that freedom is the point |
| adding a `[claim]` key to a recipe | that claim's root moves; other claims are untouched |
| changing the identity computation itself | **every** root moves; a format-version bump, never silent |
| renaming a CLI verb or flag | no root moves; a compatibility break for scripts |
| changing the kernel's Python API | pinned by the acceptance suite, so it cannot happen quietly |

The third-to-last row is the one to watch. The identity computation is
specified in [`spec/identity.md`](../spec/identity.md) precisely enough to
reimplement, and this repository ships a second implementation of it
(`conformance/reference_seal.py`) kept independent of the kernel so the two
must agree on every root. A change there is a format event.

## What is most stable today

**The kernel's public API**, oddly enough — more stable than the CLI. It is
pinned by an executable acceptance suite that two independently synthesized
implementations have satisfied, so it cannot drift without something failing
loudly.

**The identity computation**, which has one shape and an in-band digest name,
and is independently implemented twice.

Least stable: CLI verb and flag spellings, report field names, and anything
`ret assess` prints. New rungs are still being added.

## What we will do at 1.0

- Freeze the identity computation, or bump `format` when it changes and ship a
  converter that attests old-root ↔ new-root rather than pretending they are
  the same.
- Keep CLI verbs stable, with deprecation before removal.
- State which report fields are contractual and which are presentation.

Until then: pin a commit, and re-verify after upgrading rather than assuming.

## Supported platforms

Exercised in CI on macOS and Linux, CPython 3.11–3.13. Windows is untested
and would run **without a sandbox** — the isolation layer covers macOS
seatbelt and Linux bubblewrap only. Where no sandbox exists the fact is
recorded rather than faked, so a claim verified on such a host says so, but
gates there are unconfined code execution.
