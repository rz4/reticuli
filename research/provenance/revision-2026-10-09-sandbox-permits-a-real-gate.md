# Revision — the jail must permit a real gate (the user-lookup plank)

*2026-10-09. Keyholder-signed, from the r16 claude succession. A seventh
plank on run_check's jail floor; the run layer moves alone. Verified to
bite r16 and pass the shipped implementation before landing.*

    old root  2d10271449f3693a6379c3e031f5601e3aa485f991193a4cba15d1bf3a805975
    new root  71fd7559e9e9d1569cefc4f32f546509d1c3808bf7ebfe33c94f271342fd16b2

    run moves alone; nineteen layers hold.

## What moved and why

r16 (claude) cleared identity for the first time any claude draw has —
its implementation-as-content re-earns the root under full substitution.
It then failed bootstrap's audit_repo: the regrown tool AS THE AUDITOR
ran the repository's chain-rebuilding gate under its own run.py seatbelt
profile, built `(deny default)` with a minimal allowlist. That profile
passes every probe the run layer's own floor already had (/dev/null, a
subprocess, reading the host, uname) but refuses the user-database
lookup Python makes under the hood — `pwd.getpwuid(os.getuid())` ->
opendirectoryd via mach-lookup — so REPO_OK died, with no reason
reported (r16's gate result drops the output the shipped kernel keeps).

The run criterion verified the jail DENIES correctly (no network, no
write beyond the workspace) but never that it PERMITS a real gate. The
unexercised half. `--full-gate` could not catch it either — that runs
r16 as CONTENT under the SHIPPED jail, never r16's own run.py. The seam
is reachable only through the tool-as-auditor path.

run_check's floor gains a seventh plank: a gate may look up the user it
runs as. Phrased as the PROPERTY, not a profile syntax — a conforming
kernel may allow-by-default-and-deny, or deny-by-default with a
sufficient allowlist, so long as a legitimate gate runs. It lives with
the jail, in the run layer, so RUN moves alone (687b376b -> 7d78f6b3);
build and everything above hold, a layer's root covering its own
criterion.

## Verified before landing

- Found the exact denial from the macOS sandbox log during r16's failing
  audit: `mach-lookup com.apple.system.opendirectoryd.libinfo` denied,
  and `/dev/dtracehelper` writes denied (r16 allowlists specific /dev
  literals; the shipped jail allows /dev wholesale).
- The plank bites r16's ACTUAL run.py: `run.run_gate` of the user-lookup
  returns `status: failed` (KeyError: uid not found) under r16's jail,
  `status: ok` under the shipped jail. Confirmed against both
  implementations, not a reconstructed profile.
- Surgical root-cause check: flipping ONLY r16's `_seatbelt_profile` to
  the allow-default form makes its `ret audit .` pass (rc 1 -> 0).
- New root re-earns the cold gate (repo-ok) and the deep audit; ret
  verify clean.

## The arc this marks

Six prior claude seams were in the tool AS CONTENT. This seventh is the
first in the tool AS AUDITOR, reachable only because r16 finally passed
as content. r16 failed EXACTLY ONE scored condition (audit_repo) and
passed every other it reached — identity, 104/104 held-out tests, the
full recursive step, five of six bootstrap steps including the gen-2
core rebuild. This plank is the single thing that stood between the
claude family and a first qualification; the next draw that writes a
jail permitting a real gate should clear it.
