<p align="center"><img src="logo.png" alt="reticuli" width="160"></p>

# reticuli

A verification framework for computational claims.

A **claim** is defined by its acceptance tests, pinned test data, and a build
recipe. Its identity is a content hash over exactly those — the implementation
is excluded — so the hash names an **equivalence class of programs**: anything
that passes this exact check on this exact data. The toolchain can **seal** a
claim, **verify** it by re-running its tests, **rebuild** the implementation
from the tests alone, and **crosscheck** the result across machines and
vendors. Signing is a human act over the hash.

## The three-machine test

```
 M1 original            M2 transfer             M3 rebuild
 seal + verify   ──►    export / import    ──►  regrow from tests alone
      │                      │                        │
      └──────────────────────┴────────────────────────┘
                       one root hash
        valid ⇔ one digest ∧ every test re-earned ∧ cost in envelope
```

A pass on M1 shows the claim was earned at origin. A pass on M2 shows the
record survives transfer byte-for-byte. A pass on M3 shows the tests alone
carry the software — an independent implementation lands in the same
equivalence class.

## Status: pre-bootstrap

This repository is being built by its own methodology. The specification
in [`spec/`](spec/) was extracted from the v1 implementation
([reticuli-lab](https://github.com/rz4/reticuli-lab)); the v2 kernel does not
exist yet — it will be **regrown blind** from the sealed acceptance suite, and
the transcript, cost ledger, and crosscheck of that rebuild will be committed
here as the kernel's origin record. See
[`provenance/bootstrap.md`](provenance/bootstrap.md).

## Layout

| path | contents |
|---|---|
| `spec/claim-format.md` | the claim format: schema and field semantics |
| `spec/identity.md` | the root hash computation, with a worked example |
| `spec/verification.md` | seal / verify / rebuild / crosscheck / audit semantics |
| `provenance/` | how this repository came to exist, checkably |

## Lineage

v2 of [reticuli-lab](https://github.com/rz4/reticuli-lab), which remains the
research lab. v2 keeps the invariant and changes the vocabulary: plain
computer science is canonical here, on every surface and in the format itself.
