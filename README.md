<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

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

## Status: the kernel was regrown, and the toolchain is built on it

This repository is built by its own methodology. The specification in
[`spec/`](spec/) was extracted from the v1 implementation
([reticuli-lab](https://github.com/rz4/reticuli-lab)); the v2 kernel was then
**regrown blind** — by a producer that saw only the acceptance suite — and
the seed claim was sealed by the regrown kernel's own `seal()`, at a root the
independent bootstrap sealer computes identically.

**That claim passed the three-machine test**: M1 the original, M2 a byte copy,
M3 a second blind rebuild by a different vendor — one root, every verdict
re-earned, and the same verdict returned by all three independent kernels.
Byte-reuse is distinguished from independence by the build digest.
Independence itself is *not* claimed: two vendors is evidence, not proof, and
the result says so in those words. See
[`docs/provenance/crosscheck-2026-09-15.md`](docs/provenance/crosscheck-2026-09-15.md).

**That proven claim is `d64cc301…`, kept intact at
[`conformance/kernel-2.0/`](conformance/kernel-2.0/).** The kernel claim was then revised
— `4b90feef…`, in `conformance/kernel/` — to pin seven behaviors that a day of building on
it proved were under-specified, two of which the two blind rebuilds visibly
disagreed about ([`revision`](docs/provenance/revision-2026-09-15.md)). The proof
did not transfer, so it was **re-earned**: a fresh cross-vendor blind rebuild
against the revised suite passed both sandbox environments first try, and the
revised claim now carries its own three-machine proof
([`crosscheck`](docs/provenance/crosscheck-v21-2026-09-15.md)).

That second crosscheck came with a dissent worth reading: of three
independent kernels asked to judge it, two said satisfied and one did not —
its `audit` fails on the self-referential kernel claim alone. The gates were
verified by hand, without any judge, so the majority is right; but it costs
the crosscheck the property that its verdict is independent of the
implementation that produced it, and that is recorded rather than smoothed
over.

The rest of the toolchain (exchange, authoring, agents, launcher, CLI) is
built on that kernel, each layer with its own acceptance check.

`conformance/kernel/` is the sealed claim the package must satisfy;
`conformance/kernel-2.0/` is its proven predecessor, frozen and never edited;
`src/reticuli/` is the living package.
[`tests/kernel_parity.py`](tests/kernel_parity.py) keeps them honest by having
the sealed claim judge the living bytes. Ledgers, caveats, and what each
rebuild taught us: [`docs/provenance/`](docs/provenance/bootstrap.md).

## Layout

| path | contents |
|---|---|
| `src/reticuli/` | the package: kernel, exchange, authoring, agents, launcher, CLI |
| `src/reticuli/producers/` | producers a rebuild can invoke (a producer need not be a model) |
| `tests/` | ordinary tests — freely editable |
| `conformance/` | the acceptance suites. **Identity-bearing**: their bytes sit inside claim hashes, so editing one renames a claim rather than fixing a test |
| `conformance/kernel/` | the sealed claim `src/reticuli/kernel.py` must satisfy |
| `conformance/kernel-2.0/` | its proven predecessor, frozen |
| `conformance/reference_seal.py` | a second, independent implementation of `spec/identity.md`, kept so the two must agree |
| `spec/` | the format, the identity computation, verification semantics, the layer map |
| `examples/` | worked claims: `tomli` (flagship), `make` (producer = a compiler, no model), `self` (self-hosting), `quirkcalc` (toy) |
| `scripts/` | developer scripts |
| `docs/provenance/` | how this repository came to exist, checkably |

Try it — a claim whose name survives a rewrite:

```
$ python3 conformance/reference_seal.py verify examples/quirkcalc
ok quirkcalc 03d039ca6878609359e5770866377edf40a26eff48bdb1147e300aecee26f175
```

Rewrite `calc.py` however you like: if the 59 cases still pass, the root —
the claim's name — does not move. Change one byte of one case and it does.

The same idea on real software —
[`examples/tomli/`](examples/tomli/README.md) claims *a conforming TOML 1.0.0
parser*, judged by 709 cases from the external
[toml-test](https://github.com/toml-lang/toml-test) corpus. tomli 2.3.1 and
CPython's stdlib `tomllib` (3.11, 3.13, 3.14) are all members: swap any of
them in and the claim still verifies at the same root. tomli **2.4.1** is
not — it scores 700/709, because 2.4.0 deliberately adopted TOML 1.1.0. Which
versions implement the standard you depend on stops being a changelog
question and becomes a verdict with the failing cases attached.

The toolchain, from a session to a signed claim:

```
$ PYTHONPATH=src python3 -m reticuli --help
  init / hooks / status        a session and its trace
  run / seal / verify          author a claim and check its identity
  export / import / audit      move it, and re-earn its verdicts elsewhere
  rebuild / crosscheck         regrow it; run the three-machine test
  attest / sign                vouch for it; authorize it with a key
  pack / pull / tree / claims   compose claims out of claims
```

Run the acceptance suites and the tests the way CI does:

```
$ for f in conformance/*_check.py tests/*.py; do python3 "$f"; done
```

## Start here

[`docs/quickstart.md`](docs/quickstart.md) — ten minutes, no API key, no model.

**A producer does not have to be a language model.** In
[`examples/make/`](examples/make/README.md) it is a compiler: two different
compiler settings produce two different binaries that carry the same root,
because the identity is over what was demanded and verified, not over what
came out of the compiler. Used that way this is a build verifier, and nothing
about it requires a model.

## Lineage

v2 of [reticuli-lab](https://github.com/rz4/reticuli-lab), which remains the
research lab. v2 keeps the invariant and changes the vocabulary: plain
computer science is canonical here, on every surface and in the format itself.
