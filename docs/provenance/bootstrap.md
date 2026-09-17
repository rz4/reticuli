# Bootstrap: how this repository comes to exist

This repo is built by its own methodology, and this file records how —
including the parts that cannot be blind.

## The plan

1. **Spec extraction** (done first, in the lab): `spec/` was written by
   reading the v1 implementation and its acceptance suite in
   [reticuli-lab](https://github.com/rz4/reticuli-lab). Extraction is not
   blind — the extractor had full access to v1 source. Blindness applies to
   the *rebuild*, not the spec.
2. **Seed claim**: the v1 kernel's acceptance suite, translated to v2
   vocabulary and the v2 claim format, sealed as a claim whose generated
   output is the kernel itself. Its root is the first v2 identity ever
   computed — necessarily computed by v1 tooling, a residue this file
   exists to record.
3. **Blind rebuild**: a producer that has never seen the v1 kernel source
   regrows `src/reticuli/kernel.py` against the seed claim's gates —
   cross-vendor where possible, cost ledger recorded, transcript committed
   under `docs/provenance/`. If the rebuild cannot land, the spec was wrong;
   the gap goes back into `spec/` and the attempt's ledger stays here as
   evidence either way.
4. **Shell growth**: exchange, authoring, CLI, launcher — each layer ported
   or regrown against its own acceptance check, sealed as it lands.
5. **Lineage binding**: kept v1 specimens are re-sealed as v2 claims and
   each (v1 root ↔ v2 root) pair is attested and signed. Signing is the
   human keyholder's act; no agent signs.

## Honesty notes

- v2 roots do not equal v1 roots — the format keys are renamed, and key
  names are inside the hash preimage. The correspondence is attested, not
  hash-equal, by design.
- The LICENSE file is carried verbatim from v1 (institutional licensing
  pending) and is pinned as a seed alongside `logo.png`, as in v1's vessel
  layer: the law and the mark travel inside the identity.

## Ledger of what has actually happened

| date | event |
|---|---|
| 2026-09-15 | repo created: spec drafts extracted from v1 (`kernel.py` at reticuli-lab main `2ac4889`), README, this file |
| 2026-09-15 | open identity/format questions decided (preimage prefixes `input:`/`pinned:`, in-band `digest`, `claim.toml`, class defaults) — recorded in `spec/` |
| 2026-09-15 | `conformance/reference_seal.py` written by hand from the spec: root/seal/verify only, no gate runner or sandbox. The regrown kernel must agree with it on every root — a two-implementation conformance check |
| 2026-09-15 | **first v2 root**: `examples/quirkcalc` sealed at `03d039ca6878…` (gate earned manually — 59/59 cases — then sealed; the sealer runs no gates). Root invariant under implementation rewrite, changed by a one-byte fixture edit. v1 root of the same claim: `dc3c695f…` (first v1↔v2 attestation pair) |
| 2026-09-15 | **seed claim authored** (`conformance/kernel/`): the v1 kernel acceptance check (1,117 lines, reticuli-lab `checks/kernel_check.py`) translated to v2 vocabulary per `spec/kernel-api.md`. Translation was mechanical + audited: AST node sequence identical to v1 (7,627 nodes — no logic, ordering, or count changed); the six golden root vectors recomputed under the v2 preimage with `conformance/reference_seal.py` (two re-verified independently), so the seed check and the bootstrap sealer now pin each other; build-digest vectors unchanged (preimage has no recipe text). Signature namespace values carried from v1 pending the open namespace decision. The claim is DRAFT: no kernel exists; the gate cannot run until the blind rebuild |
| 2026-09-15 | **phase 4 foundation**: `src/reticuli/` becomes the living package (kernel copied byte-identical out of the sealed `conformance/kernel/`), and `tests/kernel_parity.py` makes the sealed claim judge it — `audit(seed, produce_from={…src bytes})`, the kernel's own composed-audit path, with the SEALED kernel as judge so a broken kernel is never the authority on itself. Negative-controlled: sabotage fails it, restore passes it. A survey of what the v1 shell asked of the kernel found the gap is exactly six PRIVATE helpers (`_copy`, `_h`, `_ledger_add`, `_out`, `_read`, `_seeds`) — every public API it needs is present. **The blind rebuild therefore enforced a layering v1 only assumed**: a kernel regrown from its check owes nothing to callers of its privates. Those helpers now live in `src/reticuli/_util.py`, and no layer imports a kernel private |
| 2026-09-15 | **phase 4 layers ported** (agents, launcher, authoring, exchange), each against its own translated acceptance check. The launcher port fixed a v1 layering inversion (the jester drove the CLI, a layer above it; the launcher calls the kernel in-process) and now selects generated outputs by class, so stripping can no longer delete a pinned output. The agents check's deferred cross-layer section self-activated the moment authoring landed, its verdict bytes moving from `agents-ok chain=pending` to `agents-ok` |
| 2026-09-15 | **first hand edit to the LIVING kernel** (`src/`; `conformance/kernel/` remains pristine machine-regrown). The authoring port's check failed on `cost()["seconds"]` and traced it to a real loss: v1 totalled wall-clock, but the kernel's own check never pinned it — the authoring check did, one layer up — so the blind rebuild legitimately dropped it, killing the cost envelope's last-resort unit. Restored via a `COST_UNITS` set distinct from the producer-reportable `COST_KEYS` (wall-clock is the kernel's measurement, never a self-report). **Root unchanged**: parity still earns `d64cc301…`, so the claim's equivalence class absorbed a real behavioral change. The general lesson is now in `spec/verification.md` |
| 2026-09-15 | **surface layer ported — phase 4 complete.** 18 CLI verbs, the v1 alias bridge deleted (the retired verb names now exit 2, asserted). The port found and fixed a v1 surface bug (`mint --check` declared `--signers` and silently dropped it, so an anchored verify could never report `authorized`), and reported a **cross-machine identity hazard** in the authoring layer without touching it: candidate inputs were tested with `os.path.isfile`, which folds case on macOS, so the shell token `ok` was pinned as an input because a file `OK` existed — the same session sealing to different roots on different filesystems. Fixed by matching every path component against real directory entries, pinned by a new assertion in the authoring check (negative-controlled), and written up in `spec/identity.md`. One information loss recorded rather than papered over: v2's `crosscheck` reports no per-machine environment map, so a host missing a declared requirement shows as a bare audit failure — worth pinning one layer down |
| 2026-09-16 | **v2.2 REVISION: the kernel claim moves `4b90feef…` → `e650b524…`.** Three pins, each measured first: no symlink or `..` component in a declared path (the two identity implementations disagreed on internal links — one sealed, one refused — and an internal link aliases generated bytes as pinned ones); records as crosscheck legs (spec/record.md: one predicate, two transports; durable proofs embed anchored signer identities or refuse); and a complete audit report on a claim whose gate is itself a kernel (finding 12, the v2.1 dissent). The revised suite passed against the living kernel first try; only the kernel layer's self-claim root moved. The v2.1 proof stays with `4b90feef…`; this claim is sealed, unproven, awaiting a fresh cross-vendor rebuild. Full account: `revision-2026-09-16.md` |
| 2026-09-15 | **the revised claim is PROVEN.** `gpt-5` rebuilt blind against the 1,351-line revised suite and passed both sandbox environments **first try** (895 lines, 12 min, $3.40) — the environment matrix turning the previous three-round, $18.50 search into one pass. Round 3's old kernel fails the revised suite (`seal` returning `None`), so the proof genuinely could not be inherited. M1/M2/M3 share root `4b90feef…`, all verdicts re-earned, reuse proven (`971830be15…` vs `4530ed4e83…`); proof recorded, root unmoved, phase `sealed`. **But the judges DISAGREED this time**: the living and birth kernels say satisfied, the new gpt-5 kernel says not — its `audit` fails only on the self-referential kernel claim. Verified by hand-auditing M1 and M3 without any judge; the majority is right and the dissent is a defect the suite does not pin (finding 12). Full account: `crosscheck-v21-2026-09-15.md` |
| 2026-09-15 | **v2.1 REVISION: the kernel claim moves `d64cc301…` → `4b90feef…`.** Seven measured under-specifications pinned (sandbox-apply signal, writable gate TMPDIR/HOME, wall-clock in `cost()`, the strongest-unit envelope ladder, `seal()`'s return, `rebuild` refusing a dirty target, the passing status string); four others left deliberately free. Every new assertion bite-tested; the ORIGINAL regrown kernel fails four of them — evidence the revision has content. The proven predecessor is kept intact and still verifying at `conformance/kernel-2.0/`, because its kernel predates the fixes and could not have earned the revised suite in place. **The three-machine proof does not transfer**: the current claim is sealed with no proof until fresh cross-vendor rebuilds re-earn it. Only the kernel layer of the self-hosting chain moved. Full account: `revision-2026-09-15.md` |
| 2026-09-15 | **THE THREE-MACHINE TEST IS SATISFIED (claim d64cc301…, now at `conformance/kernel-2.0/`).** `gpt-5` round 3, run under an environment matrix, passed in BOTH sandbox environments (862 lines). M1 `conformance/kernel/` (opus-regrown), M2 byte copy, M3 gpt-5 rebuild: one root `d64cc301…`, every verdict re-earned, reuse proven (M1/M2 digest `8dc2b79198…` vs M3 `78ffa584d2…`). Judged independently by all three kernels — opus-regrown, gpt-5-regrown, and the living package — all `satisfied = true`. Proof recorded as residue on M1; root unmoved; phase stays `sealed` (signing is the keyholder's). Three rounds, $18.50, 3.3M tokens. Independence still unestablished and labelled as such. Full account: `crosscheck-2026-09-15.md` |
| 2026-09-15 | **cross-vendor round 1**: `gpt-5` blind rebuild landed on the SAME root `d64cc301…` (833-line kernel, $5.83, 20 min) — one digest, two vendors. The crosscheck then caught an environment-relative conformance divergence (escaping-gate contract under an inherited jail) and correctly refused the proof; round 2 was stopped by hand mid-run. Full account: `rebuild-gpt5-2026-09-15.md` |
| 2026-09-15 | **the kernel exists — blind rebuild landed.** `claude-opus-5` at max effort, fresh context, in a room holding only the seed claim, regrew `reticuli/kernel.py` (1,451 lines) + `__init__.py`; gate earned (10 runs incl. 4 negative-control checks of the check itself); re-earned independently by the orchestrator and again inside `conformance/kernel/`. **Seed claim sealed by the regrown kernel's own `seal()` at root `d64cc301082f…`** — bootstrap sealer and regrown kernel agree on the root (two hands, one digest; 12/12 golden vectors first probe). 156,991 tokens, ~20.4 min, ledger + caveats (instructed confinement, same-vendor) in `rebuild-2026-09-15.md`. Independence unestablished — cross-vendor rebuild open |
