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

An implementation in any language conforms to the identity computation
exactly when it reproduces every expected value. A wrong separator choice, a
float routed through 64-bit binary, an unescaped non-ASCII character, or an
implementation that reads only one recipe name each fails a specific vector
by a specific amount — the vectors are the spec's teeth for implementations
this repository's own suite cannot reach.

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

These directories are sealed content: their bytes are pinned into this
repository's own root, so editing a vector renames the repository —
deliberately. Regenerate expected values only when the identity computation
itself is deliberately revised, and say so loudly.
