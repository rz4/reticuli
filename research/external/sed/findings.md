# POSIX sed, grade 2: the stack's first target it was not built for

2026-10-30. Research finding. No root moves; decides nothing; needs no
producer. Reproduce with `python3 research/external/sed/probe_sed.py`.

## Why sed

The project's external arm was jq, and jq was chosen *because* it ships three
independent implementations — the experiment went looking for a target shaped
like its instrument. This is the opposite: a target the instrument was not
built around. POSIX **sed**, as implemented independently by BSD
(`/usr/bin/sed`, Apple's) and GNU (`gsed` 4.9), is one documented spec written
by people who were not coordinating. It is not Python, it is not jq, and the
only thing driving it is zeta's `process` probe and `split` classifier —
**the same code the closure work just hardened, unchanged.** This is the first
evidence that "point zeta at any external target" is real rather than aspirational.

## What a divergence means

POSIX specifies sed. Where two conforming implementations produce different
output for one script-and-input, the spec left that corner undetermined — or
one implementation deviates. Either way it is negative space in a boundary
someone else wrote, surfaced by differential pressure: grade 2 on POSIX sed.
Agreement is the spec doing its job. A split is a point it does not pin, and
the kind matters — a *semantic* split (both run, different output) is sharper
and more dangerous than an *extension-only* split (one refuses), because the
semantic one is silent.

This note reports what diverges. It does **not** rule which side is correct —
that is an election (`spec/record.md`-style), the keyholder's call, not the
instrument's.

## The graded result

26 probes of corners POSIX leaves open: **14 agree, 6 semantic splits, 6
extension-only.** Both implementations agree on just over half the probed
surface; on the rest, a portable sed script behaves differently depending on
which sed runs it, and half of those differences are silent.

### Semantic divergences (both run, different output — the sharp kind)

- **`a\` append drops a trailing newline on BSD.** This is the finding worth
  keeping, because it is a corner POSIX arguably *did* specify. Both
  implementations accept the POSIX `a\<newline>text` form; given `x\n` and
  `1a\` + newline + `hello`, BSD emits `x\nhello` (no final newline on the
  appended text) and GNU emits `x\nhello\n`. Verified byte-for-byte:

  ```
  printf 'x\n' | /usr/bin/sed $'1a\\\nhello' | xxd   ->  78 0a 68656c6c6f
  printf 'x\n' | gsed       $'1a\\\nhello' | xxd   ->  78 0a 68656c6c6f 0a
  ```

  Two conforming seds disagree on the bytes they emit for the spec's own
  append form. A pipeline that counts on the trailing newline (or on its
  absence) is not portable, and nothing in the script says so.

- **`\+`, `\?`, `\|` in BRE are literals on BSD, operators on GNU — silently.**
  `s/a\+/X/` on `aaa` leaves `aaa` on BSD (\+ is a literal plus, no match) and
  gives `X` on GNU (\+ is a quantifier). Same for `\?` and `\|`. Neither
  errors; the output just differs. This is the most dangerous class: a
  portable-looking BRE does something different on each sed with no warning.

- **`\U` in the replacement is a literal `U` on BSD, uppercasing on GNU.**
  `s/.*/\U&/` on `abc` gives `Uabc` (BSD) vs `ABC` (GNU).

- **`0,/re/` address: BSD leaves the input unchanged, GNU deletes through the
  first match.** `0,/b/d` on `a\nb\nc` gives `a\nb\nc` (BSD) vs `c` (GNU).

### Extension-only (one refuses — portable sed cannot rely on it)

BSD refuses outright where GNU extends POSIX: the one-line `a`/`i`/`c` forms
(`1a hello`), `s///2g` (replace from the Nth match on), the `first~step`
address (`1~2d`), and `Q` (quit without printing). These are loud failures —
a script using them breaks visibly on BSD — so they are less hazardous than
the silent semantic splits above, but they are the same negative space: POSIX
does not require them, and the two implementations disagree on their existence.

## What it establishes, and what it does not

**Establishes.** The instrument generalises. Zeta's process probe and split
classifier, built for jq and hardened against the closure trials, met a target
chosen to be awkward for it and produced a graded, reproducible negative-space
map with no modification. The `a\` trailing-newline divergence is a concrete
finding about deployed software, reproducible in one command, in the spirit of
the jq ecosystem findings.

**Does not.** This is a hand-written probe set, not an exhaustive one — it
samples known-divergent corners, so the 14/26 agreement rate is a property of
the sample, not a coverage figure for POSIX sed. There is no blind rebuild
here (that needs a producer), so this is the *measurement* half of the
reconstruct-codebase loop, not replacement-grade. And it is grade 2 by
differential pressure between two implementations: it finds where they part,
which by the aperture argument is a lower bound on the spec's true negative
space, not the whole of it. Adding a third independent sed (busybox, or a
historical AT&T sed) would widen the aperture — the same move the jq arm made
with three implementations, available here if the finding is worth deepening.

## The honest next step

If this target is worth pursuing to replacement-grade, the missing half is a
blind rebuild: freeze a sed test corpus as the boundary, have a producer
regrow a sed from it, and probe the rebuild against BSD and GNU as oracles —
the full loop, which needs a model and a frozen corpus. This note is the
down-payment that shows the measurement half works on a stranger's tool.
