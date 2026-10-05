# Proposal — pin the jail's floor

*Staged 2026-10-05, from the r4 bootstrap's audit_repo failure. A
contract decision for the keyholder; nothing here moves a root until
signed. Sibling of free-the-producer (the producer side of the same
sandbox silence); independent of it.*

## The finding

The r4 regrown tool, asked to audit the repository, refuses REPO_OK in
about two minutes with no stated reason. The cause is its own jail: a
`(deny default)` seatbelt profile whose file-write allowance covers
only the workspace — not `/dev` — so the first gate line that
redirects to `/dev/null` dies with "Operation not permitted" (probe
reproduced directly; adding `/dev` to the allowance fixes it). The
regrown jail passes its layer's check — run_check's fixtures never
happen to touch `/dev` — and cannot judge the real repository.

Two distinct soundness problems, one seam:

1. **False refusals.** A conforming judge whose jail is tighter than
   the contract can fail TRUE criteria, and the result is
   indistinguishable from "the implementation is wrong." The original
   vocabulary has `environment` for "this host cannot judge the
   claim"; a too-tight jail converts that into `failed`, which is a
   lie about the claim.
2. **Silent diagnostics.** The regrown audit's gate rows carry no
   detail field, so the false refusal arrives without a reason — the
   refusal-detail surface is also unpinned (registered separately with
   the --json schema seam).

## What must be pinned if accepted

`run_check` exercises the floor: inside the gate quarantine, a gate
can (a) write `/dev/null`, (b) spawn a subprocess, (c) read outside
the workspace (the interpreter and its libraries live there), while
(d) the network stays denied and (e) writes outside workspace-and-/dev
stay denied. Five probes, each a one-line gate. A criteria edit — a
root move — hence the signature gate.

## The alternative, named honestly

Declare the jail's interior implementation-defined above "network
denied, workspace writable." Then a verdict's meaning depends on the
judge's unstated profile, and cross-implementation verdict transfer —
the 44,000× trade — silently requires matching jails. That reading
makes the sandbox signal pin (which names the backend) necessary but
nowhere near sufficient. The proposal recommends the pin.
