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
