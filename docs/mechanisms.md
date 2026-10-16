# Mechanisms

The isolation and judgment machinery, bottom up. Each section states what
the mechanism guarantees, how, and what it deliberately does not guarantee.
Source: [`reticuli._kernel.build`](book/reticuli/reticuli._kernel.build.md)
and [`reticuli._kernel.run`](book/reticuli/reticuli._kernel.run.md).

## Rooms

A room is a fresh directory into which a claim is materialized before
anything is judged or rebuilt in it.

- Only declared inputs are copied. Every destination path is containment-
  checked; a path that escapes the room is refused.
- Gate outputs are never copied. A gate re-earns its output from the bytes
  present; a stale output file would let a failed gate appear answered.
- For a rebuild, generated outputs are omitted (the producer must write
  them) unless explicitly threaded in, and any threading is recorded in
  the ledger.

## Environment scrub

Processes in a room run under an allowlist environment, not an inherited
one:

```
PATH, HOME, TMPDIR, LANG, LC_ALL, TZ   (+ the jail marker)
```

Everything else is dropped: credentials, API keys, proxy settings, tool
configuration. Additional variables reach a producer only if the caller
passes them explicitly (`producer_env`) — a deliberate handover, recorded,
never ambient inheritance. Gates receive no caller extras at all.

## Sandbox

Gates run inside an OS-level sandbox. Backend selection, in order:

| Platform condition | Backend |
|---|---|
| already inside a reticuli sandbox | `inherited` — run unwrapped, say so |
| macOS with `sandbox-exec` | `seatbelt` |
| Linux with usable `bwrap` | `bubblewrap` |
| otherwise | `none` — recorded in the verdict |

Sandboxes do not nest. Re-wrapping inside an existing jail would make
verdicts platform artifacts, so the inner run is marked `inherited`
instead. The backend actually used is part of every recorded verdict.

Two confinement tiers:

**Standard** — writes confined to the workspace (plus `/dev`); network
denied; reads open. Reads stay open because the interpreter, its
libraries, and the OS live outside the workspace.

**Strict** — standard, plus the user's home ground is masked: on macOS,
`/Users` and `/Volumes` become unreadable except the workspace and the
furnished-environment cache; on Linux, `/home` and `/root` are replaced
with empty filesystems and only the cache is re-bound. System paths stay
readable. Strict is the default for received claims.

What the sandbox does not guarantee: it is confinement for judging
honestly, not a boundary against a hostile kernel-level adversary. The
[threat model](threat-model.md) states the trust boundaries exactly.

Additional execution controls: a wall-clock ceiling per gate and per
producer, enforced by killing the whole process group (a forked child
holding the pipes would otherwise hang the verifier); an optional
file-size cap on written files (disk-fill protection under strict).

## Furnishing

A claim may declare an environment: a hash-pinned requirements file,
inside the root, because dependency versions decide what "passes" means.
Between materialization and judgment, a private virtual environment is
built from exactly the named artifacts — hashes required, wheels only, so
nothing executes at install time and nothing unnamed can arrive. A room
that cannot be furnished is an `environment` failure, distinct from a
verdict. Furnished environments are cached by content and remain readable
under strict confinement.

## Producer protocol

A producer is invoked as a shell command in the room. The contract is
environment-variable based:

| Variable | Direction | Meaning |
|---|---|---|
| `RETICULI_CLAIM` | in | the room path |
| `RETICULI_OUTPUT` | in | the next generated file to write |
| `RETICULI_OUTPUTS` | in | all generated outputs, JSON list |
| `RETICULI_REQUEST` | in | producer guidance, if any; excluded from the root |
| `RETICULI_USAGE` | out | path for a JSON usage report |

The usage report may carry `calls`, `tokens`, `usd`. Values must be finite
and non-negative; booleans and anything else are ignored. The kernel
ledgers what it accepts. Guidance can be withheld (`guidance=False`) to
run a rebuild blind; because guidance is outside the root, blind and
guided rebuilds target the same identity.

## Records and canonical bytes

A record is one machine's results: identity, per-gate verdicts with the
sandbox backend used, environment, measured cost. Records serialize to
canonical bytes — key-sorted, numbers carried verbatim — so equal records
are equal byte strings and any two machines' records can be compared or
digested. Validation refuses: unknown members at a version, non-hex or
wrong-length digests, verdict or sandbox values outside the vocabularies,
cost values that are boolean, negative, or not finite. The member set is
closed; extension is a version bump.

Cost comparisons use a unit ladder — `usd > tokens > calls > seconds` —
taking the strongest unit both sides measured. Wall-clock is always the
kernel's own measurement and is never accepted from a self-report.

## Verdict reuse

A re-audit may reuse a prior verdict only under an exact fingerprint
match: root, build digest, platform, interpreter. A reused verdict is
labeled `reused`, never `earned`, and names whose result it leaned on;
with no cache entry, everything is redone. Reuse is a cost optimization
with an honesty contract, not a trust shortcut.
