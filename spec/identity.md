# Identity: the root hash

**Status: draft, extracted from the v1 implementation (`kernel.claim`). Every
statement here is backed by v1 behavior; open questions are marked.**

A claim's identity — its **root** — is a SHA-256 digest computed from what the
claim *is*, not from any particular implementation of it.

## Computation

Build a string-to-string map `parts`, then hash its canonical serialization:

```
parts["recipe"]        = canonical_json(recipe)          # the parsed claim file
parts["seed:" + path]  = sha256(bytes of path)           # for each pinned input
parts["pin:"  + path]  = sha256(bytes of path)           # for each non-generated
                                                         # step output
root = sha256(canonical_json(parts))
```

where `canonical_json` is JSON with keys sorted and no insignificant
whitespace (v1: Python `json.dumps(..., sort_keys=True)`).

**In:** the recipe text (name, declared inputs, every step's kind, class, and
run command), the bytes of every pinned input (acceptance-test scripts and
fixture data), and the bytes of every pinned step output (recorded verdicts).

**Out:** the bytes of every output whose step class is `generated` (v1:
`free`). An implementation can be deleted and regrown byte-different without
changing the root.

## Consequences

1. **The root names an equivalence class.** Two implementations that pass the
   same pinned checks on the same pinned data are the same claim. Membership
   is checked by string comparison of two digests, not by diffing outputs.
2. **Criteria cannot be weakened silently.** Tests and fixtures are inside the
   hash: touch one byte of one fixture and the root changes — that is a
   different claim, not a variant.
3. **Identity is not health.** A root says what the claim is, never that it
   currently holds. Verification re-runs the gates; the deep audit
   distinguishes verdicts *earned* on present bytes from verdicts *carried*
   from the past.

## Worked example

The v1 `quirkcalc` record (59 fixture cases + one check script):

```
original root:              dc3c695f10cacbeb…
after rewriting calc.py:    dc3c695f10cacbeb…   (unchanged — generated file)
after editing one fixture:  db5b525a6492901a…   (changed — pinned input)
```

## File hashing rules (v1, carried into v2)

A hashed file must be a regular file with a single hard link (`st_nlink == 1`),
reached without traversing a symlink out of the claim directory. Every
recipe-declared path is joined under the claim root and refused if absolute,
empty, or escaping (via `..` or symlink). These rules close filesystem
aliasing attacks: a FIFO, device, socket, directory, or a hardlink to an
outside inode is refused, not hashed.

## Open questions for v2

- [ ] Key names inside the hash: v1 serializes the recipe with its v1 key
      names (`[record]`, `class = "free"`). v2 renames the format keys
      (`[claim]`, `class = "generated"`), so v2 roots differ from v1 roots
      *for that reason alone*. This is the accepted format break; the
      v1↔v2 correspondence is recorded by attestation, not by hash equality.
- [ ] Whether `parts` keys keep the `seed:`/`pin:` prefixes or rename to
      `input:`/`pinned:` (pure spelling inside the preimage; decide once,
      before the first seal).
- [ ] Digest agility: v1 is SHA-256 only. v2 should state the algorithm in
      the preimage or the manifest so a future migration is expressible.
