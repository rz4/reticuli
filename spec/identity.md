# Identity: the root hash

**Status: draft, extracted from the v1 implementation (`kernel.claim`). Every
statement here is backed by v1 behavior; open questions are marked.**

A claim's identity — its **root** — is a SHA-256 digest computed from what the
claim *is*, not from any particular implementation of it.

## Computation

Build a string-to-string map `parts`, then hash its canonical serialization:

```
parts["digest"]          = "sha256"                        # algorithm, stated in-band
parts["recipe"]          = canonical_json(recipe)          # the parsed claim file
parts["input:" + path]   = sha256(bytes of path)           # for each pinned input
parts["pinned:" + path]  = sha256(bytes of path)           # for each non-generated
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

The `quirkcalc` claim in this repo (`examples/quirkcalc/`: 59 fixture cases +
one check script), sealed by `tools/bootstrap_seal.py`:

```
sealed root:                03d039ca6878609359e5770866377edf40a26eff48bdb1147e300aecee26f175
after rewriting calc.py:    03d039ca6878…   (unchanged — generated file)
after editing one fixture:  dc965a0a6534…   (changed — pinned input)
```

The same claim under v1 identity (v1 keys, v1 preimage) had root
`dc3c695f10cacbeb…` — a v1↔v2 pair for the lineage attestation.

## File hashing rules (v1, carried into v2)

A hashed file must be a regular file with a single hard link (`st_nlink == 1`),
reached without traversing a symlink out of the claim directory. Every
recipe-declared path is joined under the claim root and refused if absolute,
empty, or escaping (via `..` or symlink). These rules close filesystem
aliasing attacks: a FIFO, device, socket, directory, or a hardlink to an
outside inode is refused, not hashed.

## Decisions (settled 2026-09-15, before the first seal)

- **Format break accepted.** v2 serializes the recipe with v2 key names
  (`[claim]`, `class = "generated"`), so v2 roots differ from v1 roots for
  that reason alone. The v1↔v2 correspondence is recorded by attestation,
  not by hash equality.
- **Preimage prefixes are `input:` / `pinned:`** (v1: `seed:` / `pin:`) —
  the preimage speaks the same vocabulary as the format.
- **The algorithm is stated in-band**: `parts["digest"] = "sha256"`. A
  future algorithm change is a new `digest` value, hence a new preimage —
  expressible without restructuring.

The first v2 root ever computed was the quirkcalc example, sealed by the
bootstrap sealer (`tools/bootstrap_seal.py`); see `provenance/bootstrap.md`.
