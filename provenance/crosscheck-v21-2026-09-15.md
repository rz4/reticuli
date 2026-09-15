# The three-machine test on the revised kernel claim — satisfied, with a dissent

Root `4b90feef318d171a842dd285c589c8f2e350f0e32627d62fa99e64a67fcfc382`
(the v2.1 claim; see `revision-2026-09-15.md`).

| machine | what it is | verdict |
|---|---|---|
| M1 | `seed/` — the claim | audited, earned |
| M2 | a byte copy of M1 | audited, earned |
| M3 | a blind cross-vendor rebuild: `gpt-5`, 895 lines, against the revised suite | audited, earned |

One root across all three, every verdict re-earned, byte-reuse proven: M1 and
M2 share build digest `971830be15…`, M3's is `4530ed4e83…`.

The proof is recorded on M1's manifest; the root did not move; the phase
stays `sealed`. Signing remains the keyholder's act.

## The rebuild

`gpt-5`, blind, in a room holding only `claim.toml` and the 1,351-line
revised suite, under the environment matrix: **895 lines, 12 minutes, 603,930
tokens, $3.40 — passing both sandbox environments on the first attempt.**
Against the previous suite the same producer needed three rounds and $18.50,
because rounds 1 and 2 each satisfied the environment they were iterated in
and broke the other. Running the gate under every host condition from the
start turned a three-round search into a single pass.

The revision also proved it could not be inherited: round 3's kernel, which
passed the *old* suite in both environments, fails the revised one at
`seal must return the manifest it wrote, not NoneType` — pin 5, one of the
two behaviors the vendors had disagreed about, biting a real independent
implementation.

## The dissent, which is the interesting part

Last time, three independent kernels judged the crosscheck and all three
returned `satisfied`. This time they do not agree:

| judge | verdict |
|---|---|
| the living kernel (`src/`) | `satisfied = true` |
| the **birth** kernel (`provenance/birth/`, a different implementation) | `satisfied = true` |
| the **new gpt-5 kernel** (M3 itself) | `satisfied = false` |

The dissent is a defect in the dissenting kernel, and it is narrow and
reproducible: its `audit()` succeeds on `examples/quirkcalc` and on
`examples/tomli` but fails on the **kernel claim specifically** — the one
whose gate is itself a kernel test that re-execs under a sandbox and runs
nested kernels. It reports `{"ok": false, "gates": [{"status": "failed",
"quarantine": null}]}` — no gate name, no root, no detail, and no sandbox
recorded.

The claim itself is fine, verified without relying on any judge: copying M1
to a fresh directory, deleting the verdict, and running the gate by hand
earns it and reproduces the pinned verdict bytes exactly; the same holds for
M3. So the gates are genuinely earned and the majority verdict is the correct
one.

**What this costs us is a claim we could make last time and cannot make now:
that the verdict is independent of the implementation that produced it.** Two
of three judges agreeing is weaker than three of three, and the honest
reading is that the acceptance suite does not pin enough about `audit` for
independent kernels to agree on a self-referential claim. That is finding
twelve, and a candidate for the next revision — the suite exercises `audit`
against small fixtures, never against a claim whose gate is a kernel.

## Ledger

| unit | value |
|---|---|
| started (UTC) | 2026-09-15T22:26:21Z |
| duration | ~12 min |
| tokens | 603,930 |
| usd | 3.40 |
| rounds | 1 |

Cost envelope: unmeasured (`comparable: null`) — both machines were built by
their own harnesses rather than through `kernel.rebuild`, so neither carries
a ledger the other can be compared against. Reported, not fabricated.

Independence: still `unestablished`, in the kernel's own words. Two vendors
is evidence, not proof; confinement in each rebuild was instructed rather
than jailed.
