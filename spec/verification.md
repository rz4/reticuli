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
byte to reproduce. Where the claim declares an `environment`
(`spec/claim-format.md`), the room is **furnished** first — a private venv
built from the hash-pinned file, wheels only — and a room that cannot be
furnished is an `environment` failure, never a verdict. Its verdict per claim is **earned** (every gate re-run
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

Where the claim declares `[claim] envelope` ceilings
(`spec/claim-format.md`), M3's measured cost must also land at or under
each declared unit it measured. The pinned envelope and the M1↔M3 band are
independent instruments: the band compares two ledgers and says nothing
when M1 carries none; the envelope compares the redo to the claim's own
in-root commitment. An unmeasured declared unit is untested, reported
rather than failed.

Independence is declared, not assumed: a crosscheck records which vendor and
model produced M3, and same-vendor rebuilds are marked as such
(`independence unestablished`).

### Legs may be frozen: records

A machine may stand in the test as a claim directory — a leg computed on the
spot by running its gates — or as a **record**, a signed statement of one
machine's results (`spec/record.md`). The two transports mix freely and must
reach the same verdict: a record is an input to the comparison, not a second
definition of it. A proof is residue on M1's manifest, so M1 must be a
directory. And while the comparison accepts any record, a **recorded proof**
refuses one whose signature the verifier's anchor does not verify, then
embeds each record's digest and signer identity — so a reader can walk from
the verdict to the signed statements beneath it. The boundary is the
transport: directory legs are the caller's own executions and need no
anchor; record legs are relayed statements whose only provenance is a
signature.

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

The blind rebuild of the kernel measured
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
  pinned; representation is not);
- **whether a kernel that APPLIES a sandbox tells the wrapped process so.**
  The check pins the receiving half — given `RETICULI_JAILED`, inherit rather
  than nest — but not the sending half, and the two independent rebuilds
  split on it: one set the signal for its gates, the other did not. It shows
  only when a gate is itself a claim runner, where the silent kernel dies with
  `sandbox_apply: Operation not permitted`. Both halves are needed for
  "sandboxes do not nest" to mean anything;
- whether `rebuild` may resume into a directory that already holds bytes.
  v1 allowed it (so a half-built component chain could continue); the
  regrown kernel refuses any non-empty target, which makes a partially built
  chain a refusal rather than a resumption. Nothing pins either behavior;
  the exchange layer keeps the reuse rule expressed and annotated, unreachable
  under the current kernel;
- `seal()`'s return value (one rebuild returned the manifest, another
  `None`; both conform);
- **how much of `audit` two independent kernels must agree on.** The suite
  exercises `audit` against small fixtures only, never against a claim whose
  gate is itself a kernel test. Measured: a conforming rebuild audits
  `examples/quirkcalc` and `examples/tomli` correctly and fails on the kernel
  claim, reporting a verdict with no gate name, no root, no detail and no
  sandbox recorded. Two of three judges then agree and one dissents — which
  costs the crosscheck the property that its verdict is independent of the
  implementation that produced it. A candidate for the next revision;
- **the kernel's public surface beyond the pinned symbols.** The check pins
  ~21 functions and a handful of constants; an implementation may export
  more. Nothing above the kernel may depend on an unpinned name — see
  `src/reticuli/_util.py` for why this rule exists and what it replaced.

These are deliberate freedom or candidates for future pinning — either way,
now they are named. Pinning any of them changes the check's bytes and
therefore every root built on it: a format-versioning event, not a patch.

## A claim guarantees only what its own check pins

Measured 2026-09-15, and the sharpest argument for layered claims we have.

v1's kernel totalled `calls`, `seconds`, `tokens`, and `usd` from every
ledger entry, and the cost envelope's unit ladder ends in wall-clock
(`usd > tokens > calls > seconds`). But the word `seconds` appears **zero
times** in the kernel's own acceptance check. The behavior was pinned one
layer up, by the authoring check (`assert c1["seconds"] == 2.0`).

So when the v2 kernel was regrown blind from the kernel check alone, nothing
required wall-clock to be totalled — and it was not. The producer chose
oracle-events-only over a narrower key set. The result was a silent
capability loss: two machines that measured only wall-clock would report
"no shared unit" instead of comparing. Nothing detected it until the
authoring layer was ported and its check failed.

The lesson generalizes past this bug: **a dependency's claim promises only
what that claim's gate re-earns.** A layer above may quietly rely on
behavior its dependency never promised, and any legitimate re-derivation of
that dependency — a rebuild, a second implementation, a refactor — may drop
it. In a codebase written by one hand this stays invisible; the moment a
component is genuinely re-derived, it surfaces. Two practical rules follow:

1. If a layer depends on a behavior, pin that behavior in the check of the
   layer that *owns* it, not only where it is consumed.
2. When a claim is under-specified relative to what callers assume, that gap
   is a finding to record (see the implementation-defined list above), not a
   detail to leave latent.

The fix here was made in the living kernel and, because the check does not
pin it, changed no root — the claim's equivalence class absorbed a real
behavioral change, which is the property this design exists to provide.

**And the fix's own first attempt was wrong, which sharpens the point.**
Restoring wall-clock to `cost()` made it a *mandatory* comparison, because
the regrown kernel compared every shared unit rather than the strongest one
— also unpinned, also a silent divergence from v1 and from this document.
Two 11-millisecond builds were suddenly gated on wall-clock at 2×
tolerance. The exchange layer's port measured the margin and reported it
rather than assuming it was fine. Both halves are now implemented as
specified: `cost()` totals wall-clock, and `COST_LADDER` compares exactly
one unit — the strongest both machines measured — so wall-clock can never
veto a comparison a stronger unit is able to make. Restoring one unpinned
behavior surfaced another; expect them in clusters.

## Open questions for v2

- [ ] Whether `crosscheck` subsumes `audit --deep` on a single machine or
      stays a distinct verb (v1 keeps them distinct; lean: keep).
- [ ] Tolerance default for the cost envelope (v1: 2.0) — restate or revisit
      with tomli-scale data.
- [ ] Signature namespace strings for `sign` (see claim-format.md).
