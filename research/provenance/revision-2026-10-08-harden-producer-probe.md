# Revision — the producer-freedom probe tests inheritance

*2026-10-08. Keyholder-signed, from r14's build non-convergence. A
correction to a landed pin (free-the-producer, the sandbox-closure
bundle), not a new seam — the fifth time this session a refusal turned
out to be a fragile instrument rather than the thing it accused.*

    old root  7710344f19c8839bd80d3ed4190c9600088521e3d15b00cf882ceee1fcff6672
    new root  0482adb5d2ef8a1dcd77bbdce1a2b8258125c286c42bed3fc1fe443438950f6d

    build moves alone; nineteen layers hold.

## The fix

The producer-freedom probe asserted a socket-binding producer simply
succeeds, guarded by `sandbox_backend() != "inherited"`. That proxy
for "this process is unconfined" is false under an outer sandbox that
denies the network without propagating RETICULI_JAILED — exactly how
the succession runner executes each layer's gate. So the probe fired
inside an inherited jail it could not see and failed a CONFORMING
claude build layer (r14), six regrowths running, looking like layer
density or a claude seam. It was neither: build_check passes the full
claude stack unsandboxed, and claude's run.py honors the jail var.

Hardened to the property the pin actually meant: the producer inherits
the CALLER's network reachability. The probe measures whether the
caller can bind a socket; if it can, the kernel's producer must too
(no jail added); if the caller is already confined, the property holds
vacuously and the probe is a no-op. Verified: passes the original and
the full claude stack unsandboxed, and no-ops under the
network-denying jail that blocked r14 — robust in every environment a
conforming kernel should pass in.

## Why it matters beyond r14

This fragility had been in the boundary since free-the-producer
landed. It did not block the codex qualifiers (r9, r11) — most likely
run-environment variance in whether their build gate was
network-denied at execution — but it was a latent correctness bug in a
pinned criterion: a conforming kernel could be refused for the host's
confinement rather than its own behavior. The hardened form removes
the variance. r14 re-runs at 0482adb5 to ask the real question it was
launched for — whether the claude family can qualify — now that the
harness artifact is gone. The build layer was NOT split; it conforms.
