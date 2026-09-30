# Revision — clicks A and J: the gate begins to close over its class

*2026-09-29. An identity-bearing transition. Two internal clicks, signed
by the keyholder as a pair.*

    old root  16297fb004733bfc2cb218aaa15086dfb1731ecaead3cdacec206126a77bbe90
    new root  706ed56b69ee94e27204bbfa161058eae978474d0abe6e70b7b4f77549099f87

## Why the root moved

The succession run (`research/provenance/rebuild-2026-09-29-succession.md`)
regrew the whole tool blind, twice, and found the repository's own gate
was not closed over the equivalence class it names: conforming
implementations that pass every layer suite could not run the
repository's own machinery, because pinned files consume behavior no
criterion pins. The finding was staged as ten clicks
(`research/proposals/close-the-gate-over-its-class.md`). The keyholder
signed two — the two that buy the most convergence per byte of check —
and this revision applies them.

**Click A — `criteria/authoring_check.py` pins the pack surface the
repository itself consumes.** `scripts/selfclaim.py` is a pinned file; it
calls `pack` with keyword arguments and three features
(`component` layering, `envelope`, `claim_format`) that the old
authoring check never exercised. Two independently regrown packs
satisfied every old case and could not build the chain. The check now
packs a claim the way selfclaim does — the keyword spelling, a declared
envelope and format-3 that must reach the recipe verbatim, and the
component form with its carried `from` step and its component travelling
in the claim's store. A conforming pack must now do what the repository's
own script needs.

**Click J — `criteria/kernel_check.py` pins rebuild against a realistic
producer.** Every working producer runs the gate in its room until it
passes, leaving the gate's output and earning residue (bytecode caches)
behind. A regrown kernel satisfied the old suite yet read that residue as
rewritten pinned bytes and refused every real producer. The check now
rebuilds with a producer that earns the gate in-room and asserts it
lands: the tamper watch's scope is the recipe and the declared inputs,
nothing more.

## What moved, exactly

Two suites changed, so two layer roots moved and the repository root
moved with them; every other layer root held (the lockfile in
`criteria/self_check.py` records both):

    crosscheck   bd46a97b…  ->  ea7f1e6b…   (carries kernel_check, click J)
    authoring    1ed3b97c…  ->  0129c54e…   (authoring_check, click A)

Both clicks were validated against the *living* implementation before the
reseal — a pin describes what already exists — `authoring_check` and the
kernel chain (`kernel_parity`) pass at the new criteria, and `gate.py`
re-earns `REPO_OK` cold at the new root.

## The reprove

Per the accept bars these are internal clicks (reseal + gate + this
recorded pair; not separately signed beyond the paired authorization
above). The reprove is the succession rerun under the new root
(`research/harness/succession/`, rerun 2026-09-29): the same blind
cross-family regrowth, now measured against a gate that is closer to
closed. The prediction the clicks make: a regrown pack now carries the
selfclaim surface, and a regrown kernel now accepts a realistic producer
— so a regrown tree should come nearer to running the repository's own
machinery than it could before. Whatever it does, it is recorded there.

## What remains open

Eight clicks of the proposal are unspent, including the general closure
check (F) that would make "the gate is closed over its class" a property
the gate enforces rather than an audit finding, and the specimens the
claude lineage alone exhibited (scrub credential leak, verdict
vocabulary, self-hosted audit diet). This revision is the first two
clicks of a longer ratchet, not its end.
