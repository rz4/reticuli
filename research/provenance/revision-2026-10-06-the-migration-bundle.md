# Revision — the migration bundle

*2026-10-06, afternoon. Keyholder-signed ("I sign them continue to
r7"), all three pins from the r6 trial. The fifth signed bundle in
three days; the largest deliberate root move the chain has ever taken,
and designed to be its last of this kind.*

    old root  5eabb96e07b77e84550e25cabca8e3eb358130b1e3636b79b3a0bbec3e6ee319
    new root  c6eac1332529ce9975dcf959b99077158b76cd4faddf26c252cff38636a0214a

    nineteen layer roots moved at once — the MIGRATION: every chained
    layer and the reference are format 3 now. core, format 3 since the
    basin revision, held.

## Click one — the chain migrates to format 3 (selfclaim + the lockfile)

Producer guidance leaves every layer root, including pack's own
supplied-step wording — the byte that let a conforming foreign pack
mint a chain-wide drift in the r6 trial. From this revision, ANY
conforming pack mints the chain's roots: the lockfile stops encoding
the original pack's prose and becomes what it always claimed to be, a
hash over criteria. The era-1 spelling stays pinned for foreign era-1
claims (authoring_check's keyless-recipe fixture); the chain simply no
longer lives in that era.

## Click two — the producer keeps the caller's HOME (build_check)

The rebuild's producer observes the caller's HOME — the probe bakes
the check's own HOME into a producer that refuses on mismatch. Freedom
has two halves: the r6 kernel ran producers unjailed with the network
reachable and every real producer still died 401, its credential
severed by a scratch HOME. The gates' opposite contract (scratch HOME,
nothing inherited) is pinned elsewhere and unchanged.

## Click three — the kill is prompt and reaches the whole tree (kernel_check)

The timeout probe's bound tightens from a generous 10 s to
limit-shaped (limit × 3 + 2), and a second probe puts the runaway in a
GRANDCHILD: a kernel that kills only the shell waits out the orphan
and fails the bound. Witness: the r6 kernel refused timeouts on the
runaway's schedule, straddling the old bound and making the chain
build scheduling-flaky — a criterion whose verdict depended on load,
now a criterion that decides.

## The shape of the move

Three criteria files and the chain's builder; nineteen roots re-pinned
mechanically from one selfclaim run; core held, which is the
migration's own control (already format 3, nothing about it changed).
Full gate and audit green at the new root; parity green across the
eight staged suites; 103/103; closure, the scanner, and the chain's
nesting all clean on the first draft — second bundle in a row with no
draft eaten. r7 runs next at the frozen new root: the first generation
whose chain roots a foreign pack can mint, whose producers keep their
credentials, and whose timeouts have teeth.
