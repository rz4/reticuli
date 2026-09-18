# The three-machine test on the v2.2 kernel claim — satisfied, with an abstention worth reading

Root `e650b524528ff3b821e48099c818f2de24d0da60a70e27dc120752da7f60e2df`
(the v2.2 claim; see `revision-2026-09-16.md`).

| machine | what it is | verdict |
|---|---|---|
| M1 | `examples/kernel/` — the claim | audited, earned |
| M2 | a byte copy of M1 | audited, earned |
| M3 | a blind cross-vendor rebuild: `gpt-5`, 709 lines, against the revised 1,570-line suite | audited, earned |

One root across all three, every verdict re-earned, byte-reuse proven: M1 and
M2 share build digest `275e936e11…`, M3's is `ff99eb6f2b…`. The proof is
recorded on M1's manifest; the root did not move; the phase stays `sealed`.
Signing remains the keyholder's act.

## The rebuild — the first M3 with a ledger

Unlike both earlier crosschecks, this M3 was built through `kernel.rebuild`,
so it carries a full ledger: the cost below is recorded residue, not
recollection.

| unit | value |
|---|---|
| tokens | 4,575,703 (final session; see the caveat) |
| usd | 25.74 (at gpt-5 list price, averaged in/out) |
| seconds | 2,406 (the kernel's own measurement of the final session) |
| producer | `openai / gpt-5`, blind workspace — declared, not proven |
| sessions | 3, of which 2 were killed by the host |

**The caveat, plainly:** the run took three sessions because the machine
twice killed the working process (once likely by sleeping; the cause of the
second kill is unknown). Each killed session's tokens went unrecorded — the
producer reports usage only at a passing gate or loop end — so the ledgered
total **understates** the true spend by two partial sessions (roughly 46 and
18 minutes of work). The resume protocol: the prior session's draft was
restored into the fresh room by the producer command itself, so each session
continued from its predecessor's bytes. Blindness holds across the resumes —
the room never contained anything but the recipe, the suite, and the
producer's own drafts.

## Three instrument failures before the first paid token

The launch failed three times, all before any API call, all free, all
findings:

1. **The shipped producer had never survived the recipe rename**: it opened
   `claim.toml` unconditionally, and nobody had run it since `reticuli.toml`
   became canonical. Fixed in the producer (two-name rule, canonical first) —
   the exact drift class the rename commit warned about, in the one file
   that was never taught the second name.
2. **The resume wrapper shadowed the package**: pre-creating `reticuli/` in
   the room put the draft ahead of the installed package on Python's path.
3. **Run by file path, the producer imported itself**: the module is named
   `openai.py`, and the script directory led the path, so
   `from openai import OpenAI` found the producer instead of the SDK.
   Both path traps closed with `python -P` (safe path).

## The false alarm, resolved by measurement

The rebuilt claim's gate passed in **2.6 seconds**, which read as a
subverted judge — the suite imports the code under test, so a hostile
`__init__.py` could neuter it at import time. Inspection found nothing:
clean init, no stray files, suite byte-identical to the pinned copy. The
decisive test was teeth, not timing: a one-character sabotage of M3's own
bytes (`reticuli.record` → `reticuli.records`) made the suite fail on
exactly the right assertion, and the honest bytes reproduced the 2.6 s pass
to the decimal. The speed is real — under an inherited jail, every fixture
gate skips the per-spawn sandbox cost. The suite is fast, not blind.

## The judges — and finding 13

| judge | verdict |
|---|---|
| the living kernel (`src/`) | `satisfied = true`; recorded the proof |
| the **regrown gpt-5 kernel** (M3 itself) | `satisfied = true` — over copies whose recipe carries the legacy name; **it cannot read `reticuli.toml` at all** |
| the **birth** kernel (`examples/kernel-2.0/`) | abstains: it predates the rename and also reads only `claim.toml` |

The accommodation is legitimate by construction — the recipe's filename is
not in the root preimage, so a legacy-named copy is the same claim, and the
regrown kernel computed the same root `e650b524…` for all three machines.
But it is also a finding:

**Finding 13: the recipe's two-name rule is pinned nowhere.** Every fixture
in the acceptance suite writes `claim.toml`, so a kernel that reads only the
legacy name conforms completely — and then cannot read the very claim it
satisfies, refusing `examples/kernel/` in band. The suite pins that old
claims stay readable and never that new ones are; the living kernel's
two-name `recipe_path` is, today, an implementation courtesy. A candidate
for the next revision, exactly as finding 12 was for this one — and one more
instance of the pattern that suite gaps surface precisely at the
self-referential claim.

## What is and is not established

Cost envelope: `comparable: null` — M1 was never produced through a rebuild
and carries no ledger, so there is no unit to compare. Reported, not
fabricated; this crosscheck's contribution is that M3, for the first time,
carries the measured half.

Independence: declared (`openai/gpt-5`, blind workspace), never proven. Two
vendors is evidence, not proof; confinement was instructed, not jailed.
