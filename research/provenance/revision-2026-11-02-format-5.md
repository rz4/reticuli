# Format 5: carried files, constrains, assembles — one bump, three obligations

2026-11-02. The root moved

    f2d49443a8604639ef7926182acf2e971944970a677ff7779514eec8aec123b5
    → 37d860185e4f6343c5da8b1382a810b11d425924bdb6f169c52197c2e3f6afb0

Three intermediate seals lived along the way, and every death was a pin
working: 4e6b60ea… fell because `criteria/core_check.py` pins `core.FORMAT`
as a seam VALUE (the cold gate refused a half-carried bump); 7f874e15… fell
because `criteria/self_check.py` pins every kernel layer's root — five
layers moved with their suites (core, recipe, seal, build, reference) and
the chain refused until the pins said so; and 77f2314b… earned a full cold
gate and an audit receipt before CI's linter demanded six mechanical
touch-ups in the new criteria text, which moved recipe, seal, and build
again (precise exception types instead of a blind catch, one parenthesized
string, one renamed loop variable — wording, but criteria wording is
identity, which is the whole doctrine). The identity layer's pin never moved
at any point: format 5 adds no preimage transform, and that stillness is
witnessed by the one layer that stood still.

An internal click under the keyholder's standing sign-off for the APEIRON
batch ("merge both PRs once CI is green, then do all the four items, I sign
off"): reseal + cold gate + this recorded pair + a room refresh after merge,
deliberately unsigned — the signature remains the keyholder's ceremony.

## Why identity moved

The APEIRON campaign's handoff
(`research/proposals/2026-11-02-apeiron-campaign-feedback.md`) carried three
format-bearing obligations, batched under one format bump exactly as it
suggested, so the chain pays one re-seal instead of three:

- **`class = "carried"`** (item 4): a file that ships but is never regrown.
  Hashed into the root, excluded from the build digest and from the
  producer's work list, materialized byte-for-byte at rebuild; a producer
  that rewrites one is refused. Witness: the campaign's package swap
  silently deleted `deployment/`, a README, and a `.gitkeep`, restored by
  hand — files with no class had no claim.
- **`[claim] constrains`** (item 1, seal-side): a pinned criterion declares
  the owned outputs it asserts properties of, and the seal refuses a
  declaration over a supplied module, naming the claim it belongs in. The
  refusable form of R33 — the audit's warning lane (PR #23) remains the
  advisory half for claims that declare nothing.
- **`[claim] assembles`** (item 2): the room that sees the composition. An
  assembly claim pins member roots in its own recipe (re-pinning a member
  moves the assembly's root), resolves members from its drawer, holds each
  to its declared root before any gate runs, and lays their shipped outputs
  into the gate's working tree. Witness: five campaign ledger entries were
  composition edges that passed every per-component gate and failed at
  assembly.

Format 5 adds **no preimage transform** — a format-5 claim hashes exactly as
format 4 would (`spec/identity.md`); the bump exists so a kernel that would
not enforce the new semantics refuses the vocabulary in words. Format 5 also
closes the class vocabulary at parse (an unknown class used to silently mean
"pinned": a typo deciding identity). Every root sealed at formats 1–4 is
unchanged; this repository's own claim stays format 4 — none of its recipe
uses the new keys.

## What moved, file by file

- `reticuli.toml` — the seven files of the new conformance vector join the
  pinned inputs.
- `spec/identity.md` — the format-5 section (same preimage, gated
  vocabulary).
- `spec/claim-format.md` — the carried class (table row + section),
  `constrains`, `assembles`, and the closed vocabulary rule.
- `spec/vectors/v15-format5-carried/` — new vector: a carried output enters
  the root like a pinned one and stays out of the build digest like a
  non-generated one. Expected root pinned from BOTH shipped implementations
  (kernel and reference agree); expected digest from the kernel, as the
  vectors check has always held.
- `criteria/recipe_check.py` — format-5 parse rules: the three keys refuse
  below format 5, the vocabulary closes at 5, a carried gate refuses, a
  constrains key must be an input.
- `criteria/seal_check.py` — constrains held to at seal: owned target seals,
  supplied target refuses naming the owner, phantom target refuses.
- `criteria/build_check.py` — carried rebuild semantics (blind to the
  producer, byte-identical arrival, rewrite refused) and assembly semantics
  (the gate judges members' shipped outputs, a drifted member refuses the
  fold, re-pinning a member moves the assembly root).
- `criteria/core_check.py` — the `FORMAT` seam value, 4 → 5.

Implementation (`src/`, generated, outside the root): kernel FORMAT = 5,
recipe validation, `_check_constrains` at seal, `_members` +
`_materialize_members` in the build layer, rebuild watching assembled files,
all four CLI producers' work lists filtered to generated outputs (a pinned or
carried output was never theirs to write), `pack --carried` plus the
files-in-no-class note. Unpinned mirrors in `tests/test_format5.py` (19
tests); `docs/compatibility.md` updated with the format-5 migration note —
on time, this once.

## What this does not decide

The handoff's remaining judgment calls stay the keyholder's: whether run
claims should migrate their reference-series digests to content keys
(`docs/criteria.md` rule 5), and whether this repository's own claim should
ever use the new vocabulary itself. Nothing in zeta moved; the companion's
boundary (`criteria/boundary_check.py`) is untouched.
