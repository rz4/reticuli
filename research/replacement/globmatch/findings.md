# The first replacement-grade blind rebuild

2026-11-02. A genuine replacement-grade result: a blind, independent,
from-scratch reimplementation shown indistinguishable from its original over a
probe demonstrably able to fail. Not a toy — the full loop, with a real model
producer, honest about every step including the one where it nearly fooled
itself.

Everything the jq, sed, and tr work did was the *measurement* half —
differential probing of implementations that already existed. This is the
first time the stack carried a blind rebuild all the way to grade 3.

## The target and the boundary

`globmatch`: `match(pattern, name) -> bool`, shell glob semantics (`*`, `?`,
`[set]`), with Python's `fnmatch.fnmatchcase` as both the original and the
grade-2 oracle — so "replacement-grade" means *indistinguishable from
fnmatch*. The boundary (`check.py` + `cases.json`) pins 20 core cases and is
deliberately silent on the edge surface: negated classes `[!...]`, a literal
`]` as `[]]`, ranges, backslash, the `^`-is-not-negation quirk, case. The
claim seals from its pinned inputs alone; the reference `globmatch.py` is
generated, excluded from the root, and never shown to the producer.

## Round 1 — the shortcut, and jq's lesson on a new target

Blind rebuild with **codex** (`--without-guidance`: only `check.py` and
`cases.json`, no reference, no hint). It landed the root in one call, 48k
tokens — and it had written:

```python
import fnmatch
def match(pattern, name):
    return fnmatch.fnmatch(name, pattern)
```

Grade 1 passed and the grade-2 probe found **zero** divergence — because the
rebuild *was* fnmatch. That is tautological grade 3, and it is exactly jq
generation 1's lookup-table finding on a fresh target: **a boundary that
admits a shortcut gets shortcut.** A capable blind producer, told to match a
standard behaviour, imports the standard library. "Replacement-grade against
the stdlib" is free and worthless when the rebuild *is* the stdlib.

## The repair — forbid the answer

The project's own move: the boundary now refuses the shortcut. `check.py` reads
`globmatch.py`'s source and asserts it imports no `fnmatch`, no stdlib `glob`,
no `pathlib`. A reconstruction must implement the matcher, not import it. This
moved the claim's root (a tightened boundary is a different, stronger claim),
exactly as the ratchet intends.

## Round 2 — a genuine reimplementation, to grade 3

Blind rebuild with codex again, same flags, against the tightened boundary.
29s, 48k tokens, one call, landed the new root. This time it wrote a real
matcher: a dynamic-programming glob matcher over parsed tokens, with its own
bracket-class parser handling negation, ranges, and the literal-`]` case —
`evidence/rebuild2-codex-fromscratch.py`. No stdlib matching.

It is **indistinguishable from fnmatch**:

- **825 well-formed cases** (33 quirky patterns × 25 revealing names): zero
  divergence.
- **14 hand-verified hard corners**, all agreeing with fnmatch, including the
  ones a from-scratch matcher usually gets wrong: `[]]` (literal `]`),
  `[!]a]` (negated class opening with `]`), `[[:digit:]]` (fnmatch does *not*
  treat this as a POSIX class, and neither does the rebuild), `[a-]`/`[-a]`
  (literal dash), `[z-a]` (empty reverse range), and `[^a]` — where it
  correctly treats `^` as a **literal member**, not negation (only `!` negates
  in glob; `^` is a regex habit that a naive matcher imports).

## The probe is shown able to fail

A clean grade-3 claim is worth nothing without a probe that can catch the
errors it is certifying absent. The probe mutates the rebuild's **own source**
— the mutation-testing move pointed at the artifact — injecting each error
class a from-scratch glob matcher is prone to, and confirms every one is
caught on the same case set:

| injected into codex's source | divergences caught |
|---|---|
| drop negation (`[!x]` → `[x]`) | 86 |
| exclusive ranges (`<=` → `<`) | 44 |
| `?` matches only a literal `?` | 55 |
| case-folding literals | 3 |

Each of the four classes bites; clean codex shows none. Reproduce:
`python3 research/replacement/globmatch/probe_globmatch.py <dir>`.

## What it establishes

The full reconstruct-codebase loop works end to end with a real producer: a
blind, independent model (codex — a different family from the operator) regrew
a glob matcher from criteria alone, and a probe shown able to fail cannot
distinguish it from the original across the surface it covers. **Grade 3 over
this probe.** And the arc carries the methodology's hardest lesson twice: the
first rebuild found the shortcut (convergence on the stdlib is not evidence of
a reimplementation), and the probe was only trusted after its own
discriminating power was measured against the artifact's mutations.

## What it does not

"Grade 3 **over this probe**" is the honest claim, never "grade 3" bare. The
probe covers four error classes on a curated well-formed set; a corner outside
it could still diverge, and a wider probe (or a third producer) would sharpen
the result. `fnmatch` is a small, pure, deterministic target chosen because it
*can* be driven to grade 3 in a session — the hard targets the commercial
thresholds name (behaviour entangled with environment: timing, concurrency,
crash recovery) are not reachable this way, and nothing here claims they are.
And the producer, though blind to this boundary, is not innocent of the genre:
it has seen glob matchers. That contamination does not weaken the result — a
divergence is a divergence however the code arose, and the probe measures
behaviour, not provenance — but it means this demonstrates the *loop*, not the
producer's originality.

## The cost, honestly

Two blind rebuilds, codex, ~96k tokens total, under a minute of model time.
The measurement and probe halves cost nothing but local compute. Replacement
grade on a small pure target is cheap; the thresholds doc's warning that the
price climbs with environmental entanglement stands untested here.
