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
   under `provenance/`. If the rebuild cannot land, the spec was wrong;
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
| 2026-09-15 | `tools/bootstrap_seal.py` written by hand from the spec: root/seal/verify only, no gate runner or sandbox. The regrown kernel must agree with it on every root — a two-implementation conformance check |
| 2026-09-15 | **first v2 root**: `examples/quirkcalc` sealed at `03d039ca6878…` (gate earned manually — 59/59 cases — then sealed; the sealer runs no gates). Root invariant under implementation rewrite, changed by a one-byte fixture edit. v1 root of the same claim: `dc3c695f…` (first v1↔v2 attestation pair) |
| 2026-09-15 | **seed claim authored** (`seed/`): the v1 kernel acceptance check (1,117 lines, reticuli-lab `checks/kernel_check.py`) translated to v2 vocabulary per `spec/kernel-api.md`. Translation was mechanical + audited: AST node sequence identical to v1 (7,627 nodes — no logic, ordering, or count changed); the six golden root vectors recomputed under the v2 preimage with `tools/bootstrap_seal.py` (two re-verified independently), so the seed check and the bootstrap sealer now pin each other; build-digest vectors unchanged (preimage has no recipe text). Signature namespace values carried from v1 pending the open namespace decision. The claim is DRAFT: no kernel exists; the gate cannot run until the blind rebuild |
| 2026-09-15 | **phase 4 foundation**: `src/reticuli/` becomes the living package (kernel copied byte-identical out of the sealed `seed/`), and `checks/kernel_parity.py` makes the sealed claim judge it — `audit(seed, produce_from={…src bytes})`, the kernel's own composed-audit path, with the SEALED kernel as judge so a broken kernel is never the authority on itself. Negative-controlled: sabotage fails it, restore passes it. A survey of what the v1 shell asked of the kernel found the gap is exactly six PRIVATE helpers (`_copy`, `_h`, `_ledger_add`, `_out`, `_read`, `_seeds`) — every public API it needs is present. **The blind rebuild therefore enforced a layering v1 only assumed**: a kernel regrown from its check owes nothing to callers of its privates. Those helpers now live in `src/reticuli/_util.py`, and no layer imports a kernel private |
| 2026-09-15 | **cross-vendor round 1**: `gpt-5` blind rebuild landed on the SAME root `d64cc301…` (833-line kernel, $5.83, 20 min) — one digest, two vendors. The crosscheck then caught an environment-relative conformance divergence (escaping-gate contract under an inherited jail) and correctly refused the proof; round 2 was stopped by hand mid-run. Full account: `rebuild-gpt5-2026-09-15.md` |
| 2026-09-15 | **the kernel exists — blind rebuild landed.** `claude-opus-5` at max effort, fresh context, in a room holding only the seed claim, regrew `reticuli/kernel.py` (1,451 lines) + `__init__.py`; gate earned (10 runs incl. 4 negative-control checks of the check itself); re-earned independently by the orchestrator and again inside `seed/`. **Seed claim sealed by the regrown kernel's own `seal()` at root `d64cc301082f…`** — bootstrap sealer and regrown kernel agree on the root (two hands, one digest; 12/12 golden vectors first probe). 156,991 tokens, ~20.4 min, ledger + caveats (instructed confinement, same-vendor) in `rebuild-2026-09-15.md`. Independence unestablished — cross-vendor rebuild open |
