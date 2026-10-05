# Proposal — pin the sandbox signal

*Staged 2026-10-05, from the first cross-judging run
(`research/harness/crossjudge/`). A contract decision for the
keyholder; nothing here moves a root until signed.*

## The finding

Each tool orchestrated a blind rebuild. The original's result reports
the jail the verdict was earned in (`quarantine: "seatbelt"`); both
regrown descendants report nothing — no key at all. The build-layer
criteria exercise that a rebuild runs, seals, and refuses tampering;
they never make the kernel SAY what quarantine held the gate. The
sandbox signal is therefore an unpinned seam: a descendant can earn
every verdict with no sandbox and no reader of its records would know.

The ledgered environment event has the same gap: the original writes
`quarantine` into the rebuild ledger; nothing requires it.

## Why this is worth a pin

The trust-transfer economics
(`research/provenance/experiment-2026-10-04-trust-thermodynamics.md`)
price accepting a signed verdict at ~550,000× cheaper than regrowing
it. That trade is only sane if the record says under what confinement
the verdict was earned — "ok" from an unsandboxed gate on a hostile
claim is a different fact than "ok" under seatbelt/bubblewrap. The
quarantine field is exactly the provenance a transfer-acceptor needs,
and today it is implementation-defined.

## What must be pinned if accepted

`build_check` (or `run_check`, whichever owns the seam) exercises: the
rebuild result and the audit report carry a `quarantine` field naming
the backend (`seatbelt`, `bubblewrap`, or `none` — `none` must be the
honest word, never an absent key). A criteria edit — a root move —
hence the signature gate.

## The alternative, named honestly

Declare the signal free: records need not say their confinement, and a
transfer-acceptor must re-earn locally whenever confinement matters.
That is coherent but prices away most of the transfer win. The
proposal recommends the pin.
