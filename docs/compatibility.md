# Compatibility

## Status: pre-1.0, and the format has already moved

This is a research tool. Six claim formats now exist: format 1, which is the
default, and formats 2 through 6 as opt-in extensions, described below. This
repository's own claim is format 4. Separately, the kernel's own claim has
changed identity twice, once because v2 renamed the recipe keys and once
because the acceptance suite was strengthened to pin seven behaviors it had
left free. Both moves were deliberate, and both are recorded in
[`research/provenance/`](https://github.com/rz4/reticuli/blob/main/research/provenance/bootstrap.md).

Do not build something on this that cannot tolerate a root changing. Not yet.

## The property that makes movement survivable

The recipe is inside the hash — its parsed content, canonically serialized,
so comments and layout cost nothing while a changed key or value renames the
claim. That has an unusual and useful consequence: an incompatible claim
cannot be silently misread. There is no version-skew failure in which an old
reader parses a new claim slightly wrong and proceeds. The root simply does
not match, and verification refuses.

So the compatibility story is fail-safe rather than fail-quiet. The worst
outcome of a format change is a claim that will not verify, which is loud,
rather than a claim that verifies incorrectly, which would be catastrophic.

`[claim] format` improves the diagnosis rather than the safety. A kernel
meeting a format it does not understand says so in words instead of reporting
a bare hash mismatch. Absent means 1.

**Format 2** adds `[claim] inputs_manifest`, which moves a large input list
out of the recipe and into a pinned file. Claims that do not use it stay
format 1 and keep their roots.

**Format 3** removes producer guidance, meaning `request` or `guidance` on a
produce step, from the root. A hint that helps a producer find a realization
cannot decide whether one is accepted, so it is not identity
(`spec/identity.md`). Formats 1 and 2 keep hashing the whole recipe, so their
roots are unchanged, and declaring `format = 3` opts in, making the change an
append rather than a silent reinterpretation. The examples and the kernel
claim are not at format 3, and demonstrate the older formats coexisting.

**Format 4** canonicalizes the step list the same way format 3 canonicalized
guidance. The order of `[[step]]` entries in the file cannot reject a
realization any more than a hint can, so after the format-3 strip the steps
are serialized in the lexicographic order of their canonical JSON encodings.
Two conforming authoring tools were measured emitting the same steps in
different orders and minting different roots for one claim, and that is the
defect this closes. Formats 1 through 3 keep file order, so every root sealed
under them is unchanged, and format 4 implies the format-3 strip. Declaring
`format = 4` opts in. The vectors are `spec/vectors/v12-format4-order-a` and
`-b`: the same steps in two file orders, sharing one `expected-root`.

*Migration note, recorded late on 2026-10-29.* Format 4 landed in the
repository's own claim without this page being updated, so the stability
contract described a three-format world for several weeks while the tool
shipped four, and the words "format 4" appeared nowhere in `docs/`. That
breaches this page's own promise below that a new format arrives with
migration notes and never as a silent reinterpretation. The computation was
never silently reinterpreted — formats 1 through 3 roots are untouched, and
the format number is in the root preimage, so nothing could be misread — but
the documentation of it was silently absent, which is the half of the promise
a reader depends on. There is nothing to migrate: a format-3 claim stays a
format-3 claim and keeps its root forever. Opt in by declaring `format = 4`
and resealing, which mints a new root deliberately.

**Format 5**, from 2026-11-02 and the APEIRON batch, changes nothing in the
root computation, so a format-5 claim hashes exactly as format 4 would. The
bump gates vocabulary whose semantics an older kernel would not enforce: the
`carried` step class, for files that ship but are never regrown, copied
byte-for-byte at rebuild and outside the producer's work list; `[claim]
constrains`, where a criterion declares which owned outputs it constrains,
held to at seal; and `[claim] assembles`, for a claim whose gates judge the
composition of other claims' shipped outputs, each member held to its
declared root. Format 5 also closes the class vocabulary, so an unknown class
string refuses at parse instead of silently meaning "pinned". Every root
sealed at formats 1 through 4 is unchanged, and a kernel older than format 5
refuses the new keys in words, which is the gate's purpose. The vector is
`spec/vectors/v15-format5-carried` and the rules are in
`spec/claim-format.md`. Opt in by declaring `format = 5` and resealing.

**Format 6**, from 2026-11-04, is the first format that **withdraws** a rule
rather than adding one, because the rule was unsound.

Format 4 sorts the step list into the preimage, on the ground that order is
authoring form and cannot reject a realization. Gates run in file order in
one shared workspace and gate outputs are never materialized into a room, so
a gate that reads what an earlier gate wrote makes the order decide. Two
claims differing only in that order were measured sealing to one root with
one auditing `earned` and the other `failed` — and the independent reference
implementation agreed on that root, which placed the defect in the
specification rather than in either implementation.

At format 6 the preimage keeps file order, so those are two claims. Format 6
also commits the owner-execute bit of each generated output into the build
digest, because content alone does not determine whether a gate can run its
own output: `chmod 644` left the digest byte-identical while the audit went
to `Permission denied`.

Every root and every build digest sealed at formats 1 through 5 is
unchanged, and both order vectors for format 4 still share one
`expected-root`. Formats 4 and 5 cannot be repaired without breaking roots
already sealed under them, so they keep sorting and are protected instead by
a **seal-time refusal**: a format-4/5 recipe whose gate command names an
output an earlier gate declares is now refused at parse, with a message
naming format 6 as the fix. That refusal is sound but incomplete — it reads
commands, and a command can reach a file through a variable or a script — and
`spec/claim-format.md` states the limit rather than implying coverage it does
not have. A claim already sealed at format 4 or 5 with a hidden ordering
dependency remains unsound; no root is withdrawn.

Opt in by declaring `format = 6` and resealing. The vectors are
`spec/vectors/v16-format6-order-a` and `-b`, which carry the same steps in
different orders and have **different** expected roots, and
`v17-format6-exec-bit`, which pins the triple form of the build digest.

**A tightening that is not a format bump.** A declared cost ceiling
(`[claim] envelope`) must now be **finite**. TOML admits `inf` and `nan`, and
the crosscheck compares `paid <= ceiling`, so a claim could publish an
apparently hard budget that bound nothing, or one nothing could satisfy. Both
are refused at parse, with the same bar a record's cost value and a declared
`tolerance` have always had to meet. A recipe carrying `usd = inf` no longer
parses — it never named a real ceiling, and nothing that parsed before and
still names one is affected.

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
specified in
[`spec/identity.md`](https://github.com/rz4/reticuli/blob/main/spec/identity.md)
precisely enough to reimplement, and this repository ships a second
implementation of it (`reticuli.reference`) kept independent of the kernel so
the two have to agree on every root. A change there is a format event.

## What is most stable today

The kernel's public API is the most stable surface, which is surprising,
since it is more stable than the CLI. It is pinned by an executable
acceptance suite that two independently synthesized implementations have
satisfied, so it cannot drift without something failing loudly.

The identity computation is next. It has one shape and an in-band digest
name, and it is independently implemented twice.

Least stable are CLI verb and flag spellings, report field names, and
anything `ret assess` prints, since new rungs are still being added.

## The promise

Standing as of v2.0.0, rather than deferred to some future milestone:

- **Formats are append-only, and readers keep reading every past format
  forever.** A claim sealed under format 1 verifies under every future
  kernel, both recipe filenames (`reticuli.toml`, and the older `claim.toml`)
  stay readable, and a future format is a new number with migration notes,
  never a silent reinterpretation.
- **The identity computation changes only with a format bump.** Old roots and
  new roots are related by attestation, meaning a recorded old-to-new pair,
  never by a converter pretending they are the same claim. Fresh conformance
  vectors land beside the old ones.
- **`spec/vectors/` is the contract's executable form.** A reader in any
  language that reproduces every expected value there conforms to the
  serialization and preimage rules the set covers, and vectors are only
  added, or superseded alongside a format bump. Passing the set is necessary
  and not sufficient: it is all positive roots, and the refusal surface of
  `spec/identity.md` is not yet expressible in the vector format, so an
  implementation can pass every vector and still seal a claim the
  specification says must be refused. `spec/vectors/README.md` names the
  uncovered cases. This bullet claimed "conformant exactly when" until
  2026-10-29.
- **Two machine surfaces, two tiers of promise.** The record
  (`spec/record.md`) is the durable, cross-version contract, the artifact
  other programs and parties rely on across releases, versioned by its own
  `record` field. Two record versions exist. Version 2, from 2026-09-28, adds
  the `claim` member carrying the claim's declared obligations, so a
  crosscheck over records enforces what one over directories would. Version-1
  records stay readable, and a version-1 M1 yields an incomplete verdict on
  the declared-conditions check rather than a silent pass. `--json` is the
  stable envelope, `{command, ok, status, root, data}`, for scripting a given
  release: safe to parse, but bound to that release rather than promised
  across major versions. Every other line `ret` prints is presentation and
  may change without notice.
- **CLI verbs and flags get deprecation before removal**, from v2.0.0 on.

Releases are tagged, so pin a tag and re-verify after upgrading rather than
assuming. Claims themselves are versioned by content hash, and a root moving
when criteria change is the design working rather than the promise breaking.

## Re-running work

The kernel never memoizes. `audit` re-runs the gates, always, because a
stored "it passed" is exactly the testimony this system replaces.

`ret audit --reuse` is an opt-in local shortcut that sits outside the kernel.
It skips only when this machine has already earned this claim with these
exact generated bytes under this platform, sandbox and interpreter. The root
alone is not enough, since a root deliberately admits many implementations.
It reports `verdict = "reused"` with the time the work was really done, never
`earned`, and it caches passes only, because a stale failure must never
suppress a run that would now succeed.

It cannot see a gate that reaches outside the sandbox, whether to the clock,
the network, or a file elsewhere on the host. Such a gate is not a function
of its claim, and reuse would hide that, which is why it is opt-in.

## Supported platforms

Exercised in CI on macOS and Linux, CPython 3.11 through 3.13. On Windows the
identity half works, since `verify`, roots, and reading records are pure
hashing and parsing, and the judging half refuses in words: gates need
process groups, `sh`, and a POSIX sandbox, so `audit`, `rebuild`, and
`mutation_score` raise an in-band refusal naming the platform rather than
dying in a traceback. Where a POSIX host has no sandbox, that fact is
recorded rather than faked, so a claim verified on such a host says so, but
gates there are unconfined code execution.
