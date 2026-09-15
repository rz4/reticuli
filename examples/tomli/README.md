# The flagship claim: a conforming TOML 1.0.0 parser

Root `b76212b1d2bfbf9d8716bc9aafa35778e0f006e7426f65b83df07f8213fef318`,
claim name `toml-1.0.0`.

This claim is not about a library. It is about a **behavior**: parsing TOML
1.0.0 correctly, as the ecosystem defines correctness. The judge is
[toml-test](https://github.com/toml-lang/toml-test), a conformance corpus
maintained by people who have never heard of this project — 709 cases (208
valid documents with their expected parses, 501 documents that must be
rejected), exactly the file list in toml-test's `files-toml-1.0.0`.

The parser is `class = "generated"`, so **its bytes are not in the root**.
Everything that decides pass or fail — the harness, all 917 corpus files, the
recipe — is pinned and inside it.

## Why that matters: one root, several real programs

The root names an equivalence class, and the class has real, independently
shipped members:

| implementation | result |
|---|---|
| tomli 2.3.1 (vendored here, MIT) | 709/709 |
| CPython 3.11 stdlib `tomllib` | 709/709 |
| CPython 3.13 stdlib `tomllib` | 709/709 |
| CPython 3.14 stdlib `tomllib` | 709/709 |

These are different programs — 133 differing source lines between the
vendored parser and 3.14's `tomllib`, four distinct source digests. Copy any
of them over `tomli/` and the claim still verifies at `b76212b1…`. The
identity does not move, because the identity was never about the code.

## What the claim caught

**tomli 2.4.1 — the current release — is not a TOML 1.0.0 parser**, and this
claim says so mechanically: **700/709**, naming every deviation.

```
invalid/datetime/no-secs           accepted an invalid document
invalid/local-datetime/no-secs     accepted an invalid document
invalid/local-time/no-secs         accepted an invalid document
invalid/inline-table/linebreak-01..04   accepted an invalid document
invalid/inline-table/trailing-comma     accepted an invalid document
invalid/string/basic-byte-escapes       accepted an invalid document
```

This is not a bug. tomli 2.4.0 deliberately adopted **TOML 1.1.0**, which
permits omitted seconds, newlines and trailing commas inside inline tables,
and `\xHH` escapes. The library is fine; it is simply no longer a member of
*this* claim. A claim over `files-toml-1.1.0` would be a different root — one
that stdlib `tomllib` would fail until CPython ships 1.1.0 support.

That is the point of the example. "Which versions of this dependency actually
implement the standard I rely on?" is normally answered by reading changelogs.
Here it is answered by running a gate, and the answer is a verdict with the
failing cases attached.

## The harness is the claim boundary

`check_toml.py` is pinned, so how it judges is part of the claim's identity:

- it **imports the claim's own bytes** — it evicts any loaded `tomli`,
  prepends the claim directory, and refuses to run unless `tomli.__file__`
  resolves inside the claim, so a package installed elsewhere can never be
  judged by accident;
- comparisons are **semantic, never textual**: floats as floats (`nan`
  equals `nan`, `-0.0 == 0.0`), datetimes as instants with fractional seconds
  truncated to six digits, key order irrelevant, and exact type discipline so
  a bool cannot pass as an integer;
- a rejection counts only when the parser raises its own decode error (or a
  UTF-8 decode error on the nine non-UTF-8 fixtures, where refusing the bytes
  *is* the correct verdict). A `RecursionError` or `MemoryError` is recorded
  as a failure, never mistaken for a principled refusal;
- the expected counts (208 valid, 501 invalid) are **hard-coded in the pinned
  harness**, so deleting an inconvenient case fails the gate instead of
  quietly shrinking the claim.

## Try it

```
$ cd examples/tomli && python3 check_toml.py
toml-ok 709/709 TOML 1.0.0 cases (208 valid, 501 invalid)

$ python3 tools/bootstrap_seal.py verify examples/tomli      # from the repo root
ok toml-1.0.0 b76212b1d2bfbf9d8716bc9aafa35778e0f006e7426f65b83df07f8213fef318
```

Then replace `tomli/*.py` with your Python's `tomllib` and run both again.
The gate still passes and the root does not move.

## Licensing

tomli and toml-test are both MIT. Both licenses are pinned inputs
(`LICENSE-tomli`, `LICENSE-toml-test`): third-party code travels with its
license inside the claim's identity.
