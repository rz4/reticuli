# Revision — the named target, and a bound that decides

*2026-10-06, night. Keyholder-signed ("I sign off start the next r"),
both pins from the r8 trial — the trial where a regrown implementation
re-earned REPO_OK for the first time and failed on exactly one plank.
Seventh signed bundle in four days.*

    old root  47ee199b97e41c96d6c585bd61af5db67d56cfb2c7db896b9d75ce3c295a269c
    new root  d37cd91daf732e9c60b67a68be464520c74c198e159d518651974931e34aa28c

    build      (the named target)
    crosscheck (the runaway-relative kill bound)
    the other eighteen layers hold.

## Click one — the producer is told which output to write

`build_check` gains a MULTI-OUTPUT fixture: two generated outputs, a
producer that asserts `RETICULI_OUTPUT` is set, is absolute, and names
one of the claim's own outputs, and that `RETICULI_OUTPUTS` lists them
all. Witness: the r8 kernel named the target only when a claim had
exactly one generated output, and relatively at that — so it could
satisfy every pinned producer fixture in the boundary (all of which
had a single output) and still be unable to drive a producer on any
layer of this repository's own chain. `core_check` pinned the
variables' spelling; this pins that they are there and what they mean.

Fourth plank of the producer-environment contract: the jail
(free-the-producer), HOME (the-producer-keeps-its-home), and now the
target. Each found by a different generation choosing a different
defensible shortcut.

## Click two — the kill is measured against the runaway

`kernel_check`'s promptness bound was 10 s two days ago (too loose: a
kernel refusing on the runaway's schedule straddled it, r6), then
limit-shaped at 5 s yesterday (too tight: it failed under nested load
while measuring a kernel whose kill WAS prompt, r8). Both probes now
bound the refusal against the runaway — a 30-second gate refused in
under half that time cannot have been waited out — which is the
property actually worth pinning: the ceiling bounds the work, not the
paperwork. Robust to seconds of load; still decisive by a factor of
two.

Three attempts to find one criterion's honest form, each miss found by
an instrument rather than by review. Worth keeping in the write-up as
the clearest case of what the method costs when the measurement itself
is hard.

## The shape of the move

Two criteria, two layer roots, eighteen holding; full gate and audit
green at the new root; parity across the eight staged suites; 103/103;
closure and the scanner clean on the first draft. The research
harness's own step caps — still calibrated to the old half-hour
window — were raised in the same pass, which is tooling and not
identity.

r9 runs next at the frozen new root. Every reason any generation was
ever refused is now closed: seven identity reasons (r4–r7), the
producer's jail, HOME, and target (r6–r8), and the two flaky bounds. If
the convergence reading is right, this is the generation that starts
the count.
