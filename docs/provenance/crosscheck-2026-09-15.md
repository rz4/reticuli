# The three-machine test on the kernel claim — satisfied

Root `d64cc301082f420f4541150618d8774c0ea6c1fc7015b15ce7fd001343ccb405`.

| machine | what it is | verdict |
|---|---|---|
| M1 | `conformance/kernel/` — the claim, kernel regrown blind by `claude-opus-5` | audited, earned |
| M2 | a byte copy of M1 | audited, earned |
| M3 | a second blind rebuild, cross-vendor: `gpt-5`, 862 lines | audited, earned |

**One root across all three. Every verdict re-earned on its own bytes.**
Byte-reuse is proven and distinguished from independence: M1 and M2 share a
build digest (`8dc2b79198…`); M3's differs (`78ffa584d2…`) — a genuinely
different implementation of the same claim.

## Judged three times, by three kernels

The verdict does not rest on the implementation that produced it. The same
crosscheck was run by the Opus-regrown kernel, by the GPT-5-regrown kernel,
and by the living package. All three returned `satisfied = true`, one root,
`reuse = true`, all three machines audited. Two independently rebuilt
kernels agreeing on a verdict about themselves is the strongest form of this
result we can produce on one host.

The proof is recorded as residue on M1's manifest (`kind: crosscheck`, the
two digests, timestamp). The root did not move — a manifest carries
identity, and a proof is evidence beside it, never part of the name. The
claim's phase stays `sealed`: a recorded proof is not an authorization.
Signing remains the keyholder's act.

## What it took: three rounds, and what each taught

| round | result | tokens | usd | note |
|---|---|---|---|---|
| 1 | passed bare, **failed** sandbox-inherited | 1,036,037 | 5.83 | landed the same root on the first try |
| 2 | passed sandbox-inherited, **failed** bare | 684,750 | 3.85 | the mirror image — it traded one for the other |
| 3 | **passed both** | 1,568,216 | 8.82 | run under an environment matrix |

Total cross-vendor spend: **$18.50**, 3.3M tokens.

Rounds 1 and 2 are the finding. A producer only ever sees the environment it
runs in, but the acceptance check pins behavior in *both*: where a sandbox
exists an escaping gate must be refused, and where none exists it must run,
recorded rather than hidden. Iterating in one environment silently traded
away the other — twice, in opposite directions. **A single-environment pass
is environment-scoped conformance: real, but narrower than the claim.**

Round 3 changed the harness, never the claim: `RETICULI_GATE_MATRIX` runs
the same gate command under each host condition, reports them separately,
and calls success only when all pass — with the model told not to invert
behavior when one fails, but to find the rule correct in both. That worked
on the first attempt. The claim's bytes were untouched throughout, which is
why this crosscheck is valid at all.

Round 2's kernel is preserved at `m3-r2-kernel-jailed-only.py` in the run
scratch (not committed); round 1's bytes were overwritten before that
practice started and are unrecoverable — their build digest `907008983007…`
is the only surviving fingerprint.

## What is still not established

**Independence remains unestablished, and the kernel says so** — the result
carries `"unestablished: content-independence cannot be established from
content alone"`. Two different vendors produced M1 and M3, which is
evidence, not proof: both models may share training data, and confinement in
each rebuild was *instructed* rather than jailed. The honest claim is that
two independently-run producers, given only the acceptance suite, landed in
the same equivalence class — not that they could not have colluded through
their priors.

The cost envelope is unmeasured here (`comparable: null`): both rebuilds
were driven by their own harnesses rather than through `kernel.rebuild`, so
neither machine carries a ledger the other can be compared against. Reported,
not fabricated.
