# Conformance vectors for the identity computation

Each directory here is a tiny claim, and each carries the answers a
conformant implementation of [`spec/identity.md`](../identity.md) must
compute for it: `expected-root` (the claim's identity) and
`expected-build-digest` (the digest a signature binds). The values were
computed by this repository's two independent implementations
(`reticuli.kernel` and `reticuli.reference`), which agree on every one;
`criteria/vectors_check.py` keeps that true.

## Running an implementation against them

```
python3 spec/vectors/run.py --root "<command>"
python3 spec/vectors/run.py --root "<command>" --digest "<command>"
```

The command is any shell string — a binary, a script, an interpreter
invocation. The runner appends the vector directory as one argument and
reads the last 64-hex token on stdout. For example, against the reference
implementation:

```
python3 spec/vectors/run.py \
    --root "PYTHONPATH=src python3 -m reticuli.reference root"
```

An implementation in any language that reproduces every expected value
conforms **to the serialization and preimage rules these vectors cover**. A
wrong separator choice, a float routed through 64-bit binary, an unescaped
non-ASCII character, or an implementation that reads only one recipe name
each fails a specific vector by a specific amount — the vectors are the
spec's teeth for implementations this repository's own suite cannot reach.

### What this set does not yet decide

*Corrected 2026-10-29.* This section used to read "conforms to the identity
computation **exactly when** it reproduces every expected value," which
promised more than the set delivers and in the one direction that matters:
a reimplementer who read it would take 21/21 as a finished conformance
result. Every vector here is a **positive root** (plus a build digest where
one is pinned). Nothing in the set exercises the **refusal surface** of
`spec/identity.md` — a declared path that is absolute, empty, contains
`..`, or has a symlink component; a hashed file that is a FIFO, device,
socket, directory, or a hardlink with `st_nlink > 1`; a TOML date or time
value in a recipe. Those are all *refusals*, and a refusal has no root, so
the `expected-root` format cannot express one: closing this gap needs a
vector kind that pins a refusal rather than a value, which is a change to
the vector format and is staged as a dated proposal in the research tree
rather than assumed here.

So: passing every vector is necessary and not sufficient. An implementation
can be 21/21 and still *seal* claims this specification says must be
refused — which is the more dangerous failure, because a wrong root is
caught by the next crosscheck while a wrongly-admitted claim is not caught
at all.

## What the vectors pin

- **v1–v6**: the canonical root serialization — sorted keys, default
  separators, ASCII escaping, per-file hashing, `input:`/`pinned:` prefixes —
  extracted from the kernel suite's golden table.
- **rd1–rd6**: the canonical build-digest serialization — generated outputs
  only, `from` outputs excluded, absent outputs omitted, the empty list for
  none.
- **v7-canonical-name**: the recipe under its canonical name,
  `reticuli.toml`, with a root byte-equal to v1's — the filename is not in
  the preimage, and a reader that knows only the legacy `claim.toml`
  fails here (finding 13).
- **v8-big-integer**: an integer above 2^53 in the recipe — exact decimal
  serialization, refusing the float round-trip JSON suffers in some
  languages.
- **v9-envelope**: the `[claim] envelope` cost-ceiling table, and `25.0`
  pinning the float spelling.
- **v10-format3-guidance / v11-format3-request**: format-3 claims carrying
  producer guidance under each spelling (`guidance` and `request`). Both must
  land the *same* root, and the root must not depend on the guidance text —
  an implementation that fails to strip guidance at format 3 computes a
  different value and fails these two.
- **v12-format4-order-a / v12-format4-order-b**: the same steps in two
  different file orders, sharing one `expected-root` — format 4's
  canonicalization of the step list. An implementation that serializes steps
  in file order computes two different roots for one claim and fails the
  pair. (The two directories also differ in whether the `alpha.txt` step
  carries `guidance`, so they exercise "format 4 implies the format-3 strip"
  at the same time; a failure therefore does not localize to one rule, which
  is a known wart in an otherwise one-rule-per-vector set.)
- **v13-format2-manifest**: a format-2 claim whose inputs arrive through
  `inputs_manifest`. The pinned set is the manifest file **plus every path it
  lists**, so an implementation that hashes only `[claim] inputs`, or that
  hashes the manifest without expanding it, computes a different root.
  Verified to discriminate in both directions: editing a listed file moves
  the root, and so does editing the manifest's own bytes — including a
  comment line that expansion ignores but hashing must not.
- **v14-environment**: a claim declaring `[claim] environment`. That file is
  a pinned input although it is never listed under `inputs`, because
  dependency versions decide what "passes" means. An implementation that
  treats `environment` as mere metadata computes a different root.

  *v13 and v14 were added 2026-10-29. Both rules were implemented, both were
  load-bearing, and neither was covered — the exact shape of gap the
  "exactly when" sentence above was hiding.*

These directories are sealed content: their bytes are pinned into this
repository's own root, so editing a vector renames the repository —
deliberately. Regenerate expected values only when the identity computation
itself is deliberately revised, and say so loudly.
