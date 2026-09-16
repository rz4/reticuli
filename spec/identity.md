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
one check script), sealed by `conformance/reference_seal.py`:

```
sealed root:                03d039ca6878609359e5770866377edf40a26eff48bdb1147e300aecee26f175
after rewriting calc.py:    03d039ca6878…   (unchanged — generated file)
after editing one fixture:  dc965a0a6534…   (changed — pinned input)
```

The same claim under v1 identity (v1 keys, v1 preimage) had root
`dc3c695f10cacbeb…` — a v1↔v2 pair for the lineage attestation.

## A sealed claim is not source code

Everything a claim pins — its acceptance tests, its fixtures, its recorded
verdicts — is *inside* its root. So the ordinary maintenance reflexes are
destructive when applied to it: a formatter, an import sorter, a
lint autofix, a bulk rename, even a trailing-whitespace strip will change
those bytes and therefore change the claim's name. The claim does not become
wrong; it becomes a *different claim*, and every signature, proof, and
lineage link that named the old root now names nothing.

This is not hypothetical: the first CI run over this repository linted
`conformance/kernel/` and proposed reformatting the kernel's acceptance suite. Tooling
must exclude sealed claims by configuration, and verification is the
backstop — `bootstrap_seal.py verify` on a formatted claim reports
`MISMATCH`, which is the correct and only acceptable outcome.

## Identity must not depend on the host filesystem

A claim's inputs are named in its recipe, and the recipe's text is inside the
preimage — so anything that decides *which* names get declared decides the
root. Authoring learned this the hard way: it tested candidate names with
`os.path.isfile`, which folds case on macOS and Windows. The shell token `ok`
in `printf ok > OK` tested true against the file `OK`, so `ok` was pinned as
an input. The same session therefore sealed to **different roots on
different filesystems**, and the macOS-sealed claim named an input a
case-sensitive host could not find at all.

Any name a claim declares must match a real directory entry exactly, case
included. The rule generalizes: identity may depend only on bytes and on
declarations, never on what a particular host's filesystem is willing to
resolve.

## Identity is interpreter-independent

Measured 2026-09-15 on CPython 3.11.14, 3.13.12, and 3.14.3, with both
independent implementations (`conformance/reference_seal.py` and the regrown
kernel): every interpreter computes `03d039ca…` for `examples/quirkcalc`
and `4b90feef…` for `seed` (and `d64cc301…` for its predecessor at
`conformance/kernel-2.0/`). This is a property the format depends on — a root that
moved with the interpreter would make every claim local — and it
holds because the preimage is built from sorted JSON over file digests,
nothing interpreter-specific. Worth re-measuring whenever the serialization
changes.

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
bootstrap sealer (`conformance/reference_seal.py`); see `docs/provenance/bootstrap.md`.
