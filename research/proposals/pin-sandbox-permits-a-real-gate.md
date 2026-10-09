# Proposal — the sandbox must permit a real gate, not only deny the forbidden

*Staged 2026-10-09, from the r16 claude succession. The seventh claude
seam, and the one that decided r16's trial. A candidate criteria edit in
the run layer (a root move); staged for the keyholder. Measured and
surgically confirmed before staging.*

## The finding

r16 (claude) did something no claude draw had done: it PASSED the
identity full gate (24.4 min, all eighteen chain layers re-earned under
37-module substitution). The implementation-as-content is conforming.
It then failed bootstrap's `audit_repo` — the regrown tool, used AS the
auditor (`ret audit .`), could not re-earn the repository's own gate:
`REPO_OK` failed under seatbelt, and r16's audit did not even capture
why (its gate result carries only `{output, status, quarantine}`, where
the shipped kernel captures returncode and the gate's full output).

Cause, surgically confirmed: r16's `run.py` builds its seatbelt profile
as

    (version 1)(deny default)
    (allow file-read*)
    (allow file-write* <workdir/home/tmp subpaths> <dev sinks>)
    (allow process-fork)(allow process-exec)(allow sysctl-read)

A `(deny default)` profile with that minimal allowlist. It is enough for
a SIMPLE gate — a `printf`, which is all the run layer's own
`_seatbelt_usable` probe and every layer gate ever run — so the run
layer grew clean. It is NOT enough for the repository's COMPLEX gate,
which runs `gate.py` → `self_check`, rebuilding the whole twenty-layer
chain in subprocesses; that needs operations a minimal `deny default`
withholds (mach-lookup and friends). The shipped profile is
`(allow default)(deny network*)(deny file-write*)` re-allowing the
workspace — it denies the forbidden (network, writes outside the claim)
and permits everything else, so a real gate runs.

Confirmed by the cleanest possible test: copy r16's tree, flip ONLY
`_seatbelt_profile` from `(deny default)…` to the shipped
`(allow default)(deny network*)(deny file-write*)…` form, change nothing
else — r16's `ret audit .` then PASSES (rc 0, was rc 1). One function,
one policy, the whole difference. Control: the shipped tool audits the
repo cleanly in the same environment; the chain is valid and r16's
sandbox is the diverging party.

## Why the boundary did not catch it

The run layer's criterion pins that the sandbox DENIES correctly — no
network, no write outside the workspace — and exercises it with a
`printf` gate. It never runs a gate COMPLEX enough to need the broad
allowance a real gate needs, so "the sandbox permits a legitimate gate"
is the unexercised half of the deny/allow contract. And `--full-gate`
could not catch it either: that substitutes r16 as CONTENT and audits it
under the SHIPPED sandbox, never exercising r16's own `run.py`. The seam
is only reachable through the tool-as-auditor path (audit_repo), which
is exactly where it bit.

## What to pin

A run-layer fixture that runs a NON-TRIVIAL gate under the sandbox and
asserts it SUCCEEDS: a gate that spawns a subprocess, writes under a
redirected TMPDIR/HOME, and imports — the shape a real gate has — must
pass sandboxed exactly as it passes unsandboxed. The sandbox confines
writes and the network; it must not break a legitimate gate. r16's
`deny default` minimal allowlist fails this; the shipped `allow default`
passes it. Phrased as the PROPERTY (a legitimate gate survives the
sandbox), not a profile syntax — a conforming kernel may write
`allow default + deny` or `deny default + a sufficient allowlist`, as
long as a real gate runs.

Pre-signature, per the measure-before-pin rule every landed pin
followed: build the fixture and verify it FAILS against r16's `run.py`
and PASSES against the shipped `run.py` before any signature.

## The arc this marks

Six prior claude seams were in the tool AS CONTENT — can the family
PRODUCE conforming software. r16 answered that yes. This seventh seam is
the first in the tool AS AUDITOR — can the family's tool correctly JUDGE.
The obstacle moved surfaces, from producing to judging, and it is again
at the digital/material membrane (the OS sandbox), the cousin of the
producer-freedom probe. It is cleanly encodable (unlike r13) and
surgically confirmed (like r14).

## Status

SIGNED and LANDED 2026-10-09 (root 2d102714 -> 71fd7559, run layer
alone). Encoded as a seventh jail-floor plank in run_check: a gate may
look up the user it runs as (pwd.getpwuid -> opendirectoryd). Verified
before landing: the macOS sandbox log named the denial
(opendirectoryd.libinfo mach-lookup, /dev/dtracehelper); the plank bites
r16's actual run.py (run_gate status failed) and passes shipped (status
ok); flipping only r16's profile to allow-default fixes its audit. New
root re-earns the cold gate and deep audit; ret verify clean.
Provenance: revision-2026-10-09-sandbox-permits-a-real-gate.md. By the
ratchet rule this boundary change resets the qualifying count; it is the
second steering pin for the foreign family and targets the exact sole
gap between claude and a first qualification.
