# Proposal — the jail floor gains a plank: uname

*Staged 2026-10-06 (night of trial 1), from the r5-as-judge refusal.
A contract decision for the keyholder; nothing here moves a root until
signed. This extends the jail-floor pin landed hours earlier — the
floor was real, and one generation sufficed to find it incomplete.*

## The finding

The r5 tree, asked to audit the repository, refuses in fourteen
seconds: under its gate jail, `os.uname()` raises PermissionError, and
the repository's own criteria call `platform.machine()` while
ledgering a rebuild's environment — so authoring_check and
exchange_check crash inside the r5 judge and the whole gate fails. The
r5 jail passes all five probes the floor pin landed with (/dev, spawn,
reads, network denied, foreign writes denied) and still cannot host
the criteria it exists to judge. A jail can satisfy the pinned floor
and deny `sysctl`-class introspection the standard library reaches for
on the most ordinary of calls.

Found by the API, not the CLI: the r5 audit's machine-readable result
carries the full per-gate traceback; its CLI surface says only
"acceptance gate did not reproduce" — the refusal-diagnostics seam on
the register, now with a sharper statement: the DETAIL exists at the
result layer and is dropped at the presentation layer.

## What must be pinned if accepted

One more probe in `run_check`'s floor block: inside the quarantine,
`python3 -c "import platform; platform.uname()"` succeeds. (That one
call transitively requires the `sysctl`/`uname` kernel surface and is
exactly what real criteria do.) A criteria edit — a root move — hence
the signature gate.

## The honest general statement

The floor is empirical, not derivable: each plank is discovered by a
conforming jail that lacks it. Expect the list to grow by exactly one
plank per generation that chooses a stricter profile, until it stops —
and that stopping is measurable, like everything else here.

## Status

Signed by the keyholder 2026-10-06 ("I sign off. work till the r6
run") and landed the same morning as one bundle with its two siblings
(one root move; see the provenance record
revision-2026-10-06-recipe-first-bundle.md).
