# Base64 basin pilot, generation 0 — a collapsed basin (codex, 2026-09-22)

The first real generation of the reconstruction-basin contraction experiment
([`research/design/pilot-base64-preregistration.md`](../design/pilot-base64-preregistration.md)).
The result is a clean negative: on this subject and this producer, the basin is
already a single point, so there is nothing to contract. The instrument
measured that correctly, which is the pilot's real success.

## What was run

- **Subject:** `base64-c0` — a claim whose boundary `C_0` pins only the RFC 4648
  round-trip and the §10 vectors; the malformed-input surface is unspecified.
- **Producer:** codex (ChatGPT subscription, un-metered in dollars), `k = 8`
  blind rebuilds across a size ladder: 3× `gpt-6-luna`, 3× `gpt-6-sol`,
  2× `gpt-6-astra`.
- **Instrument:** `research/harness/contraction/`, survey mode.

## Result

    generation 0: R=1.0 (8/8)  S=0.104 (1 cluster)  D=0.0  U=0  A=0  Y*=0.0

All eight rebuilds converged, and all eight are the same standard-library
one-liner — `base64.b64encode(...).decode("ascii")` and
`base64.b64decode(...)` — differing only in parameter names and type hints
(hence S ≈ 0.1, not 0). Behaviorally identical on every one of the 973 probes:
zero disagreements, no questions to adjudicate.

## What it means

The subject is too well known and too well served by the standard library.
Every model, at every size, reaches for `import base64`, so the reconstructions
inherit one decoder's exact behavior — including its treatment of the whole
unspecified strictness surface. `C_0` did no work; the standard library did.
This is convergence by shared substrate, not convergence earned by the boundary
— the producer-dependence and implementation-collapse failure modes (F2, F3)
showing up together, before a single ratchet step.

The contrast with the hand-written fixtures is the lesson. Six deliberately
diverse fixtures produced a rich disagreement surface (7 classes) and a real
contraction step; eight real rebuilds of the same trivial, library-backed task
produce none. Diversity has to come from somewhere. For a memorized,
stdlib-backed subject, **family diversity would not help** — decoders of every
family would still delegate to their own base64 — so the fix is not more
producers but a subject (or a boundary) that forbids the shortcut.

## Options this leaves

1. **Forbid the standard library.** Add to `C_0` a check that rejects any
   rebuild importing `base64` (or the language's equivalent), forcing a
   from-scratch codec. The sextet arithmetic then has to be written, and the
   strictness surface reopens — the same surface the fixtures showed splits
   implementations six ways. Cheapest path to a live curve; another ~8 rebuilds.
2. **Change the subject.** Move the pilot to something less canonical and not
   library-backed — the repo's own `quirkcalc` example is built with
   deliberate quirks for exactly this reason. Slightly more setup, more
   durable signal.

Either is a keyholder decision; nothing was ratcheted. The instrument, the
runner, and the measurement are validated and ready for whichever subject the
next generation runs on.

## Generation 0 revisited — from scratch, still a point (2026-09-22)

Option 1 was taken: `C_0` revised to bar the `base64` and `binascii` modules
(AST check plus a dynamic block), new root `180d00738160`, and eight fresh blind
rebuilds run on the same size mix.

    generation 0': R=1.0 (8/8)  S=0.097 (1 cluster)  D=0.0  U=0  A=0

The same result — and a sharper finding. All eight now write real from-scratch
codecs, and all eight converge on the *same strict canonical decoder*: length a
multiple of four, padding only trailing and ≤ 2, non-alphabet characters
rejected, and — independently, in every one — the subtle **non-canonical
padding-bit check** (`value & ((1 << (2·pad)) − 1)` before the shift, or
`((1 << (8·pad)) − 1)` after; the same test either way). Behaviorally identical
on all 973 probes. The probes cover the whole open surface (whitespace,
URL-safe, bad/missing/excess padding, misplaced `=`, junk), so D = 0 is real,
not a coverage gap.

The lesson is deeper than "the stdlib collapsed it." base64 is not merely
trivial or library-backed — it is **canonically determined**: even the corners
`C_0` deliberately left open have one *right* answer, and capable models all
find it, from scratch, unprompted. Barring the shortcut did not create
ambiguity; it just made everyone write the same correct code by hand.

So the subject criterion sharpens: a contraction subject must be **genuinely
underdetermined** — it must have corners where competent, honest
implementations *legitimately* differ — not merely non-trivial or non-canonical.
base64 has no such corners for this producer family, and (by the same argument
as above) family diversity would not manufacture them. The next subject needs
real, defensible ambiguity. The repo's `examples/quirkcalc` is built with
deliberate quirks for exactly this: expression evaluation has genuinely
contested corners (precedence, associativity, division/modulo semantics,
integer behavior, unary operators, whitespace) that reasonable implementers
resolve differently. That is where a live basin — and a real contraction curve —
should first appear.
