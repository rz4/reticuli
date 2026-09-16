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
[`examples/kernel-2.0/`](examples/kernel-2.0/).** The kernel claim was then revised
— `4b90feef…`, in `examples/kernel/` — to pin seven behaviors that a day of building on
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

`examples/kernel/` is the sealed claim the package must satisfy;
`examples/kernel-2.0/` is its proven predecessor, frozen and never edited;
`src/reticuli/` is the living package.
[`conformance/kernel_parity.py`](conformance/kernel_parity.py) keeps them honest by having
the sealed claim judge the living bytes. Ledgers, caveats, and what each
rebuild taught us: [`docs/provenance/`](docs/provenance/bootstrap.md).

## Layout

The repository is arranged the way a claim is: **what decides**, **what is
free**, and **what is neither**. One rule sorts every file — *if editing it
should change what this repository claims to be, it is a criterion; otherwise
it is not.*

**Criteria — the identity.** Editing one of these makes a different, usually
stronger claim, and moves a root.

| path | contents |
|---|---|
| `spec/` | the format, the identity computation, verification semantics, the layer map |
| `conformance/` | the acceptance suites — **every file here decides something, and every one of them runs.** Their bytes sit inside claim hashes, so editing one renames a claim rather than fixing a test |

The kernel is the one layer whose raw suite is *not* here: it is written to run
only inside a claim directory and its bytes are sealed into `4b90feef…`, so it
lives in that claim and `conformance/kernel_parity.py` runs it. That is the
kernel's entry in `conformance/`.

**Implementation — free.** Rewrite any of it and no root moves. That freedom
is what the format is for.

| path | contents |
|---|---|
| `src/reticuli/` | the package: kernel, exchange, authoring, agents, launcher, CLI |
| `src/reticuli/producers/` | producers a rebuild can invoke (a producer need not be a model) |
| `src/reticuli/reference.py` | a second, independent implementation of `spec/identity.md`, kept so the two must agree — and kept from importing the rest of the package, or it would stop being a second one |

**Neither.** These change how sure you are, or explain things. None decides
what is claimed.

| path | contents |
|---|---|
| `tests/` | ordinary tests, pytest-discoverable, freely editable. Adding one changes your confidence, never the repository's identity |
| `examples/` | sealed claims, each complete and checkable on its own: `kernel` (**the claim `src/reticuli/` must satisfy**, carrying the bytes a model regrew blind), `kernel-2.0` (its proven predecessor, frozen for provenance), `tomli` (flagship), `make` (producer = a compiler, no model), `weak` (a bad claim, on purpose), `self` (self-hosting), `quirkcalc` (toy) |
| `studies/` | research output that uses the toolchain — see [`self-verification`](studies/self-verification/FINDINGS.md) |
| `scripts/` | developer tooling, kept out of `conformance/` so that directory stays exactly the criteria |
| `docs/threat-model.md` | **what a claim proves and what it does not** — read before trusting output |
| `docs/receiving.md` | someone sent you a claim: what to run and how to read it |
| `docs/producers.md` | the producer contract — a producer need not be a model |
| `docs/compatibility.md` | what is stable, what moves, and why a format break cannot be silent |
| `docs/provenance/` | how this repository came to exist, checkably |

Try it — a claim whose name survives a rewrite:

```
$ PYTHONPATH=src python3 -m reticuli.reference verify examples/quirkcalc
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

Run them the way CI does — two jobs asking two different questions:

```
$ for f in conformance/*.py; do python3 "$f"; done   # the criteria: stdlib only
$ pip install -e '.[dev]' && pytest tests/           # the tests
```

## What this does and does not prove

A claim proves: *this artifact satisfies these acceptance criteria, and here is
a measurement of how strong those criteria are.* It does **not** prove the code
is correct or safe — a backdoored implementation that passes the tests is
admitted, because the implementation is deliberately outside the hash.
[`examples/weak/`](examples/weak/README.md) shows two programs with different
behaviour carrying the same root, and
[`docs/threat-model.md`](docs/threat-model.md) states the boundaries.

## Start here

```
pip install git+https://github.com/rz4/reticuli.git
ret --help
```

Python 3.11+, no dependencies. Then
[`docs/quickstart.md`](docs/quickstart.md) — ten minutes, no API key, no
model.

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
