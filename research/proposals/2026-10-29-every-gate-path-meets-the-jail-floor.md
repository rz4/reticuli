# Every path that runs a gate meets the jail floor, not just the kernel's

2026-10-29. Staged for a keyholder signature. A **contraction**: the authored
tree passes as written once today's fixes are in, and no current member is
evicted. Not landed here.

## The measurement

`criteria/run_check.py` pins the jail floor as a **property** — seven planks,
each added by a measured refusal: a gate may sink to `/dev/null`, spawn a
subprocess, read the host it runs on, ask the host its name, look up the user
it runs as, and the network stays unreachable. That is a good criterion and it
judges exactly one caller: `kernel.run_gate`.

Three other paths ran a claim's gate command, and on 2026-10-29 all three were
found to be wrong in ways no criterion could see:

| path | what was wrong | caught by |
|---|---|---|
| `producers/{openai,anthropic}` `run_gate` tool | bare `subprocess.run(shell=True)` with the caller's whole environment | outside reading |
| `launcher.pick_sandbox` | a second profile, drifted four ways | outside reading |
| `reuse.layered_audit` | unjailed by design, but its cache key claimed a backend | outside reading |

Then the *repair* introduced four more — an ambient `RETICULI_JAILED` cleared
(exit 71 on every producer gate call), a functional probe silently dropped
(exit 71 from inside an outer jail), a legitimate write-allow lost (BSD `diff`
broken under `ret run`), and a derived strict mask that could hide
`/opt/homebrew/bin/python3`. **Every one of those passed `gate.py` and the
223-test suite.** They were found by a human-directed adversarial review of
the diff, which is not a repeatable instrument.

The common cause is placement, the same pattern r26 and r33 witnessed one
level up: the obligation lives where the kernel is judged, and the defect
lives where the kernel is *called*.

## Why the boundary currently cannot see it

`src/reticuli/producers/` is deliberately outside the root — a producer is
substrate, not identity (`reticuli.toml`, the comment before the final gate
step), and that decision is right and should stand. `launcher.py` and
`reuse.py` are `generated`, so their bytes are outside too; only their
*behavioral* criteria are inside, and no criterion asks whether they reach the
same jail floor the kernel does.

So the acceptance boundary is silent about the confinement of three of the
four paths that execute a stranger's shell command. That silence is not an
oversight in the format; it is an unpinned seam, and this project's own method
says an unpinned seam gets colonized by whatever is cheapest.

## The proposed criterion

A new plank set in `criteria/run_check.py` (or a sibling), asserting the floor
as a property of **every** gate-running path rather than of one function:

1. **One chokepoint, pinned by behavior.** For each path that runs a claim's
   gate command, the network is unreachable and writes outside the workspace
   are denied — asserted the way `run_check.py` already asserts them for
   `run_gate`, by running a probe gate through that path and reading the
   result. Concretely: a probe through the producers' shared helper, and a
   probe through the launcher's wrap.
2. **A path that is deliberately unconfined says so in machine-readable
   form.** `layered_audit` is legitimately unjailed (a layer check imports the
   package staged beside it, which the scrubbed environment cannot carry), and
   its fingerprint now records `sandbox: "plain"`. Pin that: a verdict or
   fingerprint from an unconfined run must never carry a backend name.
3. **The nesting rule is two-way on every path.** `criteria/kernel_check.py`
   already pins that a kernel applying a jail must *say* which one. The
   converse now matters too: a caller must not clear an inherited signal.
   Assert that a gate run from inside a jail reports `inherited` and succeeds,
   through each path — this is the single defect that would have cost a full
   40-turn producer session.

Plank 3 is the one with a measured witness behind it already, so it is the
cheapest to justify and the most valuable to land.

## The honest objection

Pinning the *producers* path drags vendor adapters toward the equivalence
class, which is exactly what the producer-free fixpoint exists to prevent. The
way out is to pin the **shared helper's property**, not any adapter: the
criterion can stage its own trivial producer (as `self_check`'s bootstrap half
already does with a fixed script) and assert the floor through it. What gets
pinned is "a producer's gate runs confined", which is a property of the
harness; which vendor's adapter calls it stays substrate.

Cost, stated plainly: every current reconstruction is retired when the root
moves, and the count resets by condition 7 — already 0 of 3 at this root, so
the marginal cost is as low as it will ever be. Recommended as a batch with
the refusal-vector proposal so the population retires once.
