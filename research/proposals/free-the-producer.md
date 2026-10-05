# Proposal — pin that the producer runs unconfined

*Staged 2026-10-05, from the r4 bootstrap's gen-2 failure. A contract
decision for the keyholder; nothing here moves a root until signed.*

## The finding

The r4 regrown tree cannot drive a generation-2 rebuild: its
`_produce` wraps the producer command in the same sandbox the gates
get. Under seatbelt the codex CLI dies before doing anything (its Rust
runtime cannot allocate a stack guard page inside the jail), and even
a producer that survived would find the network denied — which ends
every model-backed producer. Reproduced twice; not a flake.

Nothing pins this. The criteria pin that GATES run quarantined and
(since the sandbox-signal pin) that verdicts name their jail; they are
silent on whether the producer is confined. The regrown tree made the
defensible-sounding choice — jail everything — and the choice is
sterile: a descendant that can judge but cannot procreate. The seam is
exactly the "nested sandbox" question: the original's own doctrine
(sandboxes do not nest; `RETICULI_JAILED` means inherit, don't wrap)
exists because confinement composes badly, and the producer is the
place it composes worst.

## Why the contract should say "unconfined"

A producer is the caller's chosen oracle: it legitimately needs the
network (model calls), its own tooling, and a real process
environment. The kernel's safety story around it is already explicit
and different in kind: the environment is SCRUBBED (nothing inherited
leaks in), the tamper snapshot catches a producer that edits pinned
bytes, and the gates — which decide everything — run jailed. Confining
the producer adds no soundness (its output faces the gate regardless)
and subtracts capability (most real producers die). A caller who wants
a jailed producer can wrap its command; the kernel must not.

## What must be pinned if accepted

`build_check` exercises it: a rebuild's producer step runs with
network reachable and without a kernel-imposed jail — concretely, a
producer command that would fail under the gate sandbox (e.g. one that
binds a socket, or inspects for the jail) succeeds, while the same
probe run as a GATE is refused by the quarantine. One criteria edit —
a root move — hence the signature gate.

## The alternative, named honestly

Declare producer confinement implementation-defined. Then "rebuild
with your producer" is not a portable verb — a conforming kernel may
be unable to run any real producer — and generation-2 bootstraps are
only possible on implementations that happened to choose freedom. That
reading makes succession an accident of the draw. The proposal
recommends the pin.
