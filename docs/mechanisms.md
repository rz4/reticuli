# Mechanisms

The isolation and judgment machinery, general to specific. Each section
states what the mechanism guarantees, how it does so, and what it
deliberately does not guarantee. The source is
[`reticuli._kernel.build`](book/reticuli/reticuli._kernel.build.md) and
[`reticuli._kernel.run`](book/reticuli/reticuli._kernel.run.md).

## Rooms

A room is a fresh directory into which a claim is materialized before
anything is judged or rebuilt in it.

- Only declared inputs are copied. Every destination path is
  containment-checked, and a path that escapes the room is refused.
- Gate outputs are never copied. A gate re-earns its output from the bytes
  present, and a stale output file would let a failed gate appear answered.
- For a rebuild, generated outputs are omitted so the producer has to write
  them, unless they are explicitly threaded in, and any threading is
  recorded in the ledger.

## Environment scrub

Processes in a room run under an allowlist environment rather than an
inherited one:

```
PATH, HOME, TMPDIR, LANG, LC_ALL, TZ   (+ the jail marker)
```

Everything else is dropped: credentials, API keys, proxy settings, and tool
configuration. Additional variables reach a producer only if the caller
passes them explicitly through `producer_env`, which is a deliberate
handover and is recorded, rather than ambient inheritance. Gates receive no
caller extras at all.

## Sandbox

Gates run inside an OS-level sandbox. The backend is selected in this order:

| Platform condition | Backend |
|---|---|
| already inside a reticuli sandbox | `inherited` — run unwrapped, say so |
| macOS with `sandbox-exec` | `seatbelt` |
| Linux with usable `bwrap` | `bubblewrap` |
| otherwise | `none` — recorded in the verdict |

Sandboxes do not nest. Re-wrapping inside an existing jail would make
verdicts into platform artifacts, so the inner run is marked `inherited`
instead. The backend actually used is part of every recorded verdict.

There are two confinement tiers.

**Standard** confines writes to the workspace and `/dev`, denies the
network, and leaves reads open. Reads stay open because the interpreter, its
libraries, and the OS all live outside the workspace.

**Strict** is standard plus a mask over the user's home ground. The
directories this host actually keeps home directories in become unreadable,
along with `/Volumes` on macOS, except for the workspace and the
furnished-environment cache; under bubblewrap they are replaced with empty
filesystems and only the cache is re-bound. System paths stay readable.
Strict is the default for received claims.

The mask is derived from where `$HOME` resolves rather than from a fixed
list. Until 2026-10-29 it used the literals `/Users` and `/Volumes` on macOS
and `/home` and `/root` on Linux, which is right on a stock distribution and
masks nothing on the layouts this tool is most likely to be audited on: a
cluster's `/data/home/...`, an NFS or autofs mount, a relocated `$HOME`.
Strict that silently protects nothing while still reporting `strict` is
worse than strict that is absent. There is one special case: when `$HOME`
sits directly at the root, as `/root`, the home directory itself is masked
rather than its parent, since masking `/` would deny the interpreter and the
host.

Under bubblewrap the jail also unshares the PID and IPC namespaces and
starts a new session, where the host permits it, probed as a unit like the
backend itself and reported by `sandbox_hardened()`. Without its own PID
namespace the jail's `/proc` is the host's, so a gate could read
`/proc/<pid>/environ` of any process sharing its uid, including the `ret`
that spawned it while it holds a vendor credential for a rebuild. The
environment scrub keeps inherited secrets out of a gate's variables, and
this keeps them off the gate's `/proc`. Seatbelt needs none of it, since it
has no namespaces and governs reads directly in the profile, so
`sandbox_hardened()` is false there by construction.

What the sandbox does not guarantee is worth stating plainly: it is
confinement for judging honestly, not a boundary against a hostile
kernel-level adversary. The [threat model](threat-model.md) states the trust
boundaries exactly.

Two further execution controls apply. A wall-clock ceiling runs per gate and
per producer, enforced by killing the whole process group, because a forked
child holding the pipes would otherwise hang the verifier. An optional
file-size cap on written files provides disk-fill protection under strict.

## Furnishing

A claim may declare an environment as a hash-pinned requirements file, which
sits inside the root because dependency versions decide what "passes" means.
Between materialization and judgment, a private virtual environment is built
from exactly the named artifacts, with hashes required and wheels only, so
nothing executes at install time and nothing unnamed can arrive. A room that
cannot be furnished is an `environment` failure, which is distinct from a
verdict. Furnished environments are cached by content and remain readable
under strict confinement.

## Producer protocol

A producer is invoked as a shell command in the room, and the contract runs
through environment variables:

| Variable | Direction | Meaning |
|---|---|---|
| `RETICULI_CLAIM` | in | the room path |
| `RETICULI_OUTPUT` | in | the next generated file to write |
| `RETICULI_OUTPUTS` | in | all generated outputs, JSON list |
| `RETICULI_REQUEST` | in | producer guidance, if any; excluded from the root |
| `RETICULI_USAGE` | out | path for a JSON usage report |

The usage report may carry `calls`, `tokens`, and `usd`. Values must be
finite and non-negative, and booleans and anything else are ignored. The
kernel ledgers what it accepts. Guidance can be withheld with
`guidance=False` to run a rebuild blind, and because guidance is outside the
root, blind and guided rebuilds target the same identity.

## Records and canonical bytes

A record is one machine's results: identity, per-gate verdicts with the
sandbox backend used, environment, and measured cost. Records serialize to
canonical bytes, key-sorted with numbers carried verbatim, so equal records
are equal byte strings and any two machines' records can be compared or
digested. Validation refuses unknown members at a version, non-hex or
wrong-length digests, verdict or sandbox values outside the vocabularies,
and cost values that are boolean, negative, or not finite. The member set is
closed, and extending it means a version bump.

Cost comparisons use a unit ladder, `usd > tokens > calls > seconds`, taking
the strongest unit both sides measured. Wall-clock is always the kernel's
own measurement and is never accepted from a self-report.

## Verdict reuse

A re-audit may reuse a prior verdict only on an exact fingerprint match
across root, build digest, platform, and interpreter. A reused verdict is
labeled `reused` rather than `earned` and names whose result it leaned on,
and with no cache entry everything is redone. Reuse is a cost optimization
with an honesty contract attached, not a trust shortcut.
