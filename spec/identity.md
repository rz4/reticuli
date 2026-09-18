# Identity: the root hash

**Status: normative. Pinned in `reticuli.toml`; editing it moves the repository
root, so a change is an identity-bearing transition rather than an ordinary
edit. Open questions, where any remain, are marked inline.**

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

where `canonical_json` follows exactly these rules. They are what both
implementations (`reticuli.kernel`, `reticuli.reference`) already produce, and
the kernel suite's golden root vectors pin them — an implementation that
differs on any of them fails conformance rather than quietly computing
different names for every claim:

- **Keys sorted** by Unicode code point.
- **Default separators, not compact**: `", "` between members and `": "` after
  a key — there is a space after every colon and comma. An earlier draft of
  this file said "no insignificant whitespace", which contradicted both
  implementations; a reimplementation following that sentence would have
  computed a different root for every claim in existence.
- **Non-ASCII escaped** as `\uXXXX`, so the serialization is ASCII and its
  UTF-8 encoding changes nothing.
- **Integers in exact decimal**, arbitrary precision: an implementation that
  routes them through 64-bit floats (their default fate in JavaScript) is
  nonconforming.
- **Floats as CPython's `repr`**: the shortest decimal string that round-trips.
  A float in a recipe is legal, but it asks every future implementation to
  reproduce this formatting — recipes are safest holding integers and strings.
- **TOML date and time values are refused** at sealing: JSON gives them no
  canonical form, so they cannot enter a preimage. TOML booleans serialize as
  `true` / `false`.

Equivalently: Python `json.dumps(x, sort_keys=True)` with every other argument
left at its default, encoded UTF-8.

Note the double serialization: the recipe is serialized once into a string,
which becomes the *value* of `parts["recipe"]`, and that string is escaped
again when `parts` itself is serialized. The recipe is embedded as a JSON
string, never as a nested object.

## Format 3: producer guidance is not in the root

A produce step may carry a `guidance` string (older claims spell it
`request`) that instructs a producer how to write the output. Guidance helps
a producer *find* a realization; it is never consulted when deciding whether
one is *accepted* — the gate does that. So a byte of guidance cannot change
whether any realization passes, and by the identity rule it does not belong
in the root.

At **format 3**, the recipe is stripped of every step's `guidance` and
`request` keys before it is serialized into `parts["recipe"]`. Two claims
that differ only in how they word a producer instruction therefore have the
same root: they are the same acceptance boundary. Everything else in a step
(`kind`, `output`, `class`, `run`, `from`) and every `[claim]` field stay in
the preimage, because each can affect acceptance.

Formats 1 and 2 serialize the whole recipe, guidance included, exactly as
before — so every root sealed under them is unchanged, and both recipe
filenames stay readable. This is the compatibility promise working: a new
format, past formats readable forever, the change never silent. Both
implementations (`reticuli.kernel`, `reticuli.reference`) apply the identical
strip, so they agree on every format-3 root; the format-3 conformance
vectors in `spec/vectors/` pin it for implementations in any language.

The claim's `name` stays in the root at format 3. It cannot reject a
realization, so under the strict rule it is arguably not identity-bearing —
but it is the human label a claim travels under, and dropping it would
collapse two identically-tested but differently-named claims into one root.
Kept deliberately; revisit if a future format wants a stricter boundary.

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
one check script), sealed by `reticuli.reference`:

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
`examples/kernel/` and proposed reformatting the kernel's acceptance suite. Tooling
must exclude sealed claims by configuration, and verification is the
backstop — `bootstrap_seal.py verify` on a formatted claim reports
`MISMATCH`, which is the correct and only acceptable outcome.

## Identity must not depend on the host filesystem

A claim's inputs are named in its recipe, and the recipe is inside the
preimage — so anything that decides *which* names get declared decides the
root. It is the recipe's *parsed content* that is hashed, canonically
serialized (see the preimage above), not its bytes: comments and formatting in
a `reticuli.toml` are free, and a claim can be documented in place without
renaming itself. Authoring learned this the hard way: it tested candidate names with
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
independent implementations (`reticuli.reference` and the regrown
kernel): every interpreter computes `03d039ca…` for `examples/quirkcalc`
and `4b90feef…` for the kernel claim. This is a property the format depends
on — a root that
moved with the interpreter would make every claim local — and it
holds because the preimage is built from sorted JSON over file digests,
nothing interpreter-specific. Worth re-measuring whenever the serialization
changes.

## File hashing rules

A hashed file must be a regular file with a single hard link (`st_nlink == 1`).
A recipe-declared path is refused if it is absolute or empty, if any component
is `..`, or if any component is a symlink — even one whose target stays inside
the claim. These rules close filesystem aliasing: a FIFO, device, socket,
directory, or a hardlink to an outside inode is refused, not hashed; and an
internal symlink is refused because it can alias generated bytes as a pinned
name — sealing would hash the implementation into the root through the alias,
and materializing would deliver it into a blind rebuilder's room.

The symlink rule tightened on 2026-09-16 (the v2.2 kernel revision). v1 and
early v2 refused only a symlink whose target left the claim, and the two
identity implementations disagreed about internal links — one sealed, one
refused, so whether a claim existed depended on which kernel looked at it.
Both now refuse any symlink component, and the kernel suite pins the rule.

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
bootstrap sealer (`reticuli.reference`); the repository's provenance record
has the dated account.
