# Revision — the sandbox-closure bundle

*2026-10-05, the day's second signed bundle ("I approve the three
staged proposals"). All three pins come from the r4 generation's
discoveries, staged in the morning's record and landed before
midnight. Finding → proposal → signature → pin, twice in one day.*

    old root  344ba6e12b72191e2c250d4cecc27f29fa6ec8561f0cce0992586edcc3c27437
    new root  e2b77b87cad3c1331b38088943fbbeeaa0592b0ec90a4803e8cf04a805ee6075

    run       47a8f034…  ->  5dc85c71…   (the jail's floor)
    build     852c086b…  ->  b5385b74…   (the producer runs free)
    exchange  a5771893…  ->  c051cbe7…   (deep audit walks the whole chain)
    the other seventeen layers hold.

## Click one — the jail's floor (run_check)

Inside the gate quarantine a gate may sink to /dev, spawn a
subprocess, and read the host it runs on; the network and writes
beyond the workspace stay denied (the deny side asserted only where a
jail actually applies — `none` and `inherited` have nothing to deny
with). Witness: the r4 tree's deny-default jail blocked /dev/null and
refused TRUE criteria as `failed`, with the claim innocent and no
reason reported.

## Click two — the producer runs free (build_check)

A rebuild's producer is scrubbed but never kernel-jailed: a
socket-binding producer must succeed, where the same probe as a gate
is refused. Witness: the r4 tree jailed its producers — codex died
allocating a stack guard page, and any survivor would have found the
network denied — a descendant that judges but cannot procreate.

The pin's own first draft was refused by the chain that hosts it: run
inside a layer gate, the check IS inside a jail (`inherited`), where
the network is not the kernel's to grant. Sandboxes do not nest — the
kernel's own doctrine — so the probe yields under `inherited`,
pinning the kernel's choice and not the host's. The boundary's
machinery corrected the boundary's new sentence before it landed,
again.

## Click three — the deep audit walks the whole chain (exchange_check)

A three-claim chain (top on mid on base): the composed audit judges
EVERY ancestor, and a sabotaged grandparent — invisible to both gates
above it — fails the composed verdict. Depth propagates refusals, not
just visits. Witness: the r4 tree's audit_deep recursed one level and
reported a deep chain healthy after checking its first link; the old
two-claim fixture never forced recursion.

## The shape of the move

One bundle, three criteria files, three layer roots, no cascade —
the lockfile diff is exactly the intention, as with every click since
the reference layer was made implementation-free. Full gate and audit
green at the new root; 103/103 ordinary tests; closure and the
self-contained scanner clean on the first landed draft (their lessons
from the morning's bundle were applied in advance, and the one new
lesson — inherited jails — was caught by the chain itself).

With this bundle the sandbox contract has three pinned faces: the
verdict NAMES its jail (morning), the jail has a FLOOR (now), and the
producer is FREE of it (now). The next generation tests all three; the
cross-judging matrix is the instrument. What "the remaining nested-gate
and sandbox-signal questions" named a week ago is, tonight, three
criteria with witnesses instead of a question.
