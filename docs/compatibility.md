# Compatibility

## Status: pre-1.0, and the format has already moved

This is a research tool. Three claim formats now exist — format 1 (the
default) and formats 2 and 3 as opt-in extensions, described below; this
repository's own claim is format 3. Separately, the kernel's own claim has
changed identity twice — once because v2 renamed the recipe keys, once because
the acceptance suite was strengthened to pin seven behaviors it had left free.
Both moves were deliberate; both are recorded in
[`research/provenance/`](../research/provenance/bootstrap.md).

**Do not build something on this that cannot tolerate a root changing.** Not
yet.

## The property that makes movement survivable

The recipe is inside the hash — its parsed content, canonically serialized,
so comments and layout cost nothing but a changed key or value renames the
claim. That has an unusual and useful consequence: **an incompatible claim cannot be silently misread.** There is no
version-skew failure where an old reader parses a new claim slightly wrong and
proceeds. The root simply does not match, and verification refuses.

So the compatibility story is fail-safe rather than fail-quiet. The worst
outcome of a format change is a claim that will not verify, which is loud, not
a claim that verifies incorrectly, which would be catastrophic.

`[claim] format` improves the diagnosis rather than the safety: a kernel
meeting a format it does not understand says so in words instead of reporting
a bare hash mismatch. Absent means 1.

**Format 2** adds `[claim] inputs_manifest`, which moves a large input list out
of the recipe and into a pinned file. Claims that do not use it stay format 1
and keep their roots.

**Format 3** removes producer guidance (`request`/`guidance` on a produce
step) from the root: a hint that helps a producer find a realization cannot
decide whether one is accepted, so it is not identity (`spec/identity.md`).
Formats 1 and 2 keep hashing the whole recipe, so their roots are unchanged;
declaring `format = 3` opts in, and the change is an append, never a silent
reinterpretation. This repository's own claim is format 3; the examples and
the kernel claim are not yet, and demonstrate the older formats coexisting.

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
(`reticuli.reference`) kept independent of the kernel so the two
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

## The promise

Standing as of v2.0.0, not deferred to some future milestone:

- **Formats are append-only, and readers keep reading every past format
  forever.** A claim sealed under format 1 verifies under every future
  kernel; both recipe filenames (`reticuli.toml`, and the older `claim.toml`)
  stay readable; a future format is a new number with migration notes, never
  a silent reinterpretation.
- **The identity computation changes only with a format bump.** Old roots
  and new roots are related by attestation — a recorded old↔new pair —
  never by a converter pretending they are the same claim. Fresh conformance
  vectors land beside the old ones.
- **`spec/vectors/` is the contract's executable form.** A reader in any
  language is conformant exactly when it reproduces every expected value
  there; vectors are only added, or superseded alongside a format bump.
- **Two machine surfaces, two tiers of promise.** The record
  (`spec/record.md`) is the durable, cross-version contract: the artifact
  other programs and parties rely on across releases, versioned by its own
  `record` field. `--json` is the stable envelope
  (`{command, ok, status, root, data}`) for scripting a given release — safe
  to parse, but bound to that release, not promised across major versions.
  Every other line `ret` prints is presentation and may change without notice.
- **CLI verbs and flags get deprecation before removal**, from v2.0.0 on.

Releases are tagged; pin a tag, and re-verify after upgrading rather than
assuming. Claims themselves are versioned by content hash, and a root moving
when criteria change is the design working, not the promise breaking.

## Re-running work

The kernel never memoizes: `audit` re-runs the gates, always. A stored "it
passed" is exactly the testimony this system replaces.

`ret audit --reuse` is an opt-in local shortcut, outside the kernel. It skips
only when *this machine* has already earned *this claim* with *these exact
generated bytes* under *this platform, sandbox and interpreter* — the root
alone is not enough, since a root deliberately admits many implementations.
It reports `verdict = "reused"` with the time the work was really done, never
`earned`, and it caches passes only: a stale failure must never suppress a run
that would now succeed.

It cannot see a gate that reaches outside the sandbox — the clock, the
network, a file elsewhere on the host. Such a gate is not a function of its
claim, and reuse would hide that. Hence opt-in.

## Supported platforms

Exercised in CI on macOS and Linux, CPython 3.11–3.13. On Windows the
identity half works — `verify`, roots, reading records are pure hashing and
parsing — and the judging half **refuses in words**: gates need process
groups, `sh`, and a POSIX sandbox, so `audit`, `rebuild`, and
`mutation_score` raise an in-band refusal naming the platform rather than
dying in a traceback. Where a POSIX host has no sandbox, that fact is
recorded rather than faked, so a claim verified on such a host says so, but
gates there are unconfined code execution.
