# Verification semantics

**Status: draft, extracted from v1 (`kernel.verify`, `kernel.audit`,
`kernel.prove`, phases). v2 names; v1 semantics unless a change is called
out.**

## Verbs

| v2 | v1 | what it does |
|---|---|---|
| `seal` | condense | freeze a workspace into a claim: compute the root, write the manifest |
| `verify` | verify | re-run the claim's gates on the bytes present; identity must match |
| `rebuild` | realize | regrow the generated outputs (via a producer) until the gates pass |
| `crosscheck` | prove | the three-machine test (below) |
| `audit` | audit | deep re-earning of every verdict, composed claims included |
| `sign` | mint | a human signs the root; **never** an agent's act |

## Phases

| v2 | v1 | meaning |
|---|---|---|
| `draft` | vapor | no sealed record yet |
| `sealed` | liquid | root computed, manifest written |
| `signed` | solid | authorized **and** proven: a trusted signature over the root, coupled to a recorded crosscheck |

A recorded proof alone never advances phase, and neither does a signature
from an untrusted key. Trust is verifier-relative: with no reachable trust
anchor (an ssh `allowed_signers` file), every claim is at most `sealed`
*to you*.

## Failure classes

Every gate outcome is classified; "it failed" is never the whole verdict:

| class | meaning |
|---|---|
| `reproduced` | ran clean; pinned bytes match |
| `mismatch` | ran clean; wrong bytes — the claim does not hold |
| `failed` | nonzero exit |
| `timeout` | exceeded the gate's wall-clock bound |
| `environment` | a declared requirement is missing on this host — the host can't judge, distinct from the claim being wrong |

## Audit: earned vs. carried

`audit` deletes nothing but trusts nothing: it regrows generated outputs (no
verdicts carried in), re-runs every gate sandboxed, and requires every pinned
byte to reproduce. Its verdict per claim is **earned** (every gate re-run
clean on present bytes) or **carried or broken** (some verdict is inherited
history, not present fact). Composed claims audit recursively; the deep form
is the default, `--shallow` opts out.

## Crosscheck: the three-machine test

- **M1** — the original workspace: verify in place.
- **M2** — transfer: export, import elsewhere, verify from the received
  bytes alone.
- **M3** — independent rebuild: a producer that sees only the pinned inputs
  (tests, fixtures, recipe) regrows the generated outputs from scratch.

**Valid ⇔ one root across all three ∧ every gate re-earned ∧ the cost
envelope holds.** The cost envelope compares M3's ledger to M1's in the
strongest unit both recorded (`usd` > `tokens` > `calls` > `seconds`);
C3/C1 must be within tolerance (v1 default: 2.0). Where the claim declares a
`mutation_floor`, M3 must also re-earn it: deterministic mutants drawn from
the root, kill rate ≥ floor.

Independence is declared, not assumed: a crosscheck records which vendor and
model produced M3, and same-vendor rebuilds are marked as such
(`independence unestablished`).

### What each machine's pass shows

- **M1**: the claim was earned at origin — the tests pass on the original
  build.
- **M2**: transfer integrity — identity and verdicts re-verify from received
  bytes; nothing corrupted or substituted in transit.
- **M3**: spec sufficiency — the pinned inputs alone carry the software; an
  independent implementation lands in the same equivalence class.

### What each machine's failure isolates

- **M1 fails**: the claim never held.
- **M2 fails**: a transfer or tamper problem.
- **M3 fails**: the claim is under-specified or not independently
  reproducible — and the diff between what M3 built and what the tests
  demand maps the gap.

## Cost ledger

Every rebuild appends to a ledger: producer identity, model, calls, tokens,
usd, seconds, and the verdict environment (interpreter, platform, sandbox
status) as residue. Ledgers are evidence for the cost envelope and for the
per-layer accounting of composed claims.

## Implementation-defined behavior (measured, not guessed)

The blind rebuild of the kernel (provenance/rebuild-2026-09-15.md) measured
exactly where the acceptance suite leaves freedom — behaviors a conforming
kernel may choose, where independent implementations will differ:

- concrete store/ledger/signature-directory filenames (only their
  relationships are pinned);
- the manifest schema beyond `name`/`root`; recorded-proof content beyond
  JSON round-tripping;
- the passing gate status string (failure classes are pinned; the success
  spelling is not);
- the default gate timeout, and the cost-envelope tolerance anywhere in
  [1.5, 4.0);
- `sandbox()`'s return shape beyond the backend field;
- the `gate_deciders` heuristic beyond the pinned vectors;
- the element type of a mutation score's survivor list (determinism is
  pinned; representation is not).

These are deliberate freedom or candidates for future pinning — either way,
now they are named. Pinning any of them changes the check's bytes and
therefore every root built on it: a format-versioning event, not a patch.

## Open questions for v2

- [ ] Whether `crosscheck` subsumes `audit --deep` on a single machine or
      stays a distinct verb (v1 keeps them distinct; lean: keep).
- [ ] Tolerance default for the cost envelope (v1: 2.0) — restate or revisit
      with tomli-scale data.
- [ ] Signature namespace strings for `sign` (see claim-format.md).
