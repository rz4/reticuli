# Proposal — the producer-freedom probe tests inheritance, not absolute network

*Staged 2026-10-08, from r14's build non-convergence. A contract
decision for the keyholder; a root move (build_check), so the
signature gate. It corrects a LANDED pin (free-the-producer, the
sandbox-closure bundle), so it also fixes a latent fragility that has
been in the boundary since then.*

## The finding

r14 (claude) halted in GENERATION at the build layer: the producer's
build.py regrowth never passed build_check across six attempts (two
runs). It is NOT layer density and NOT a claude seam:

- build_check PASSES against the regrown build.py on an original lower
  stack, and against the FULL claude stack, run unsandboxed.
- claude's run.py correctly honors the inherited-jail convention
  (`sandbox_backend()` returns "inherited" when RETICULI_JAILED=="1").

The actual failure, from the ledger: `AssertionError: a socket-binding
producer succeeds: the kernel imposes no jail`. That is the
producer-freedom probe I added with free-the-producer. It runs a
rebuild whose producer binds a localhost socket and asserts success,
guarded by `if build.sandbox_backend() != "inherited"`.

The guard is wrong. It uses `sandbox_backend() != "inherited"` as a
proxy for "this process is not confined" — but the succession runner
executes the build layer's gate under an OUTER sandbox that denies the
network WITHOUT RETICULI_JAILED visible to the probe. So
`sandbox_backend()` honestly reports "seatbelt" (not inherited), the
probe runs, the producer's socket bind is denied by the OUTER jail,
and the assertion fires — through no fault of the kernel under test.
Confirmed directly: under `(deny network*)` seatbelt without
RETICULI_JAILED, the probe fires and fails on a conforming stack.

The pin conflates two different things: "the kernel ADDS no jail of
its own" (the real contract) and "the ambient environment has network"
(an environmental accident). It holds in a plain local `ret audit`
(network present) and breaks whenever build_check runs inside external
confinement — the succession per-layer gate, and potentially CI.

## What must be pinned instead

The producer must inherit the CALLER's network reachability, whatever
that is — not absolute availability. Concretely: the probe first
measures whether the CALLER can bind a localhost socket; if it can,
the rebuild's producer must too (the kernel adds no jail); if the
caller itself cannot (already confined), the property is vacuously
satisfied and the probe skips. This asserts exactly "the kernel does
not CONFINE the producer beyond what the caller already is," which is
what free-the-producer meant, and it is robust to running inside any
outer sandbox. One assertion rewrite in build_check — a root move.

## Why this did not block codex earlier (honestly, partially)

codex trees qualified (r9, r11) and regrew build through the same
runner. The cleanest read is run-environment variance: whether the
build gate's subprocess was network-denied at the moment each run
executed. I did NOT prove codex also fails the fragile probe under
external confinement (my controlled codex arm errored on an unrelated
quoting artifact before reaching the socket), so I am not claiming
"both families fail" — only that the probe is demonstrably fragile and
claude is not at fault for jail detection. The fix removes the
variance either way: the hardened probe passes in every environment a
conforming kernel should pass in.

## Status of r14

INCONCLUSIVE — blocked by this criterion fragility, not a merit
result. Not a qualifier, not a legitimate seam-refusal, not a density
problem. Re-run after the probe is hardened. The build layer is NOT to
be split; it conforms.
