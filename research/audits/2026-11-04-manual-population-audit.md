# The manual, audited by a population

*2026-11-04. Five independent agents were each given the manual, a working
`ret`, a task, and no access to this repository. Their divergences are
findings about the manual in the same way a population's divergences are
findings about a boundary. Every defect below was reproduced by hand before
being recorded; two agents disagreed with each other and the reproduction
decided it.*

## The room

Each agent received the 21 hand-written manual pages, `ret 2.0.0` installed
in its own virtualenv, and a working directory with staged artefacts. No
source, no `criteria/`, no `spec/`, no `findings/`. They were instructed not
to use prior knowledge of reticuli and to record the temptation instead.
`ret --help` was allowed, as it ships with the product.

| # | task | tier | outcome |
|---|---|---|---|
| 1 | author a claim from scratch | sonnet | completed |
| 2 | judge a claim handed to you | haiku | completed |
| 3 | regrow an implementation with no API key | opus | completed |
| 4 | diagnose and recover a tampered claim | sonnet | completed |
| 5 | decide whether a claim's tests are worth anything | haiku | completed |

All five completed their task. All five declared no leakage. One (3)
disclosed that it had spent real tokens probing `RETICULI_DRY_PROMPT`, and
that the claim's own `README.md` names the root and producer, so the room
leaks through the artefact under test.

Note the distribution: the two haiku agents found the fewest defects and the
opus agent found the most. A manual that only works for the strongest reader
is a finding in itself, and this is weak evidence in that direction — though
it is equally explained by task difficulty, since the regrow task touched
the most machinery.

## Defects in the tool, not the manual

These need `src/` changes, so they stale the signature and belong in a
signing ceremony. The manual has been amended to describe current behaviour
honestly in the meantime.

### 1. `export`/`import` does not preserve the executable bit — HIGH

Reproduced directly:

    rebuilt wordcount    -rwxr-xr-x
    after export+import  -rw-r--r--
    ret audit <imported> → failed: check.sh: ./wordcount: Permission denied

The consequence is larger than a permissions nit. Given exactly two
directories, `ret crosscheck` materializes the byte-copy leg itself through
export and import. That leg then fails its audit, and **the crosscheck
rejects for any claim whose generated output must be executable**, however
sound the rebuild was. The two-argument form documented in `make-a-claim.md`
and `how-do-i.md` therefore could not produce the exit 0 those pages showed.

It also contradicts `ret help import`: "export and import are as close to
inverses as practical."

Workaround now documented: pass three directories with a `cp -a` copy.

### 2. `verify` cannot name the moved files on a transported claim — HIGH

`verify` reports `broken — 1 pinned file(s) changed` and names them only when
the manifest carries per-file digests. A claim sealed with name and root
alone reports `broken — expected … got …`, and `-v` and `--json` add nothing
(`changed: null`).

**`.reticuli/parts.json` does not survive export/import**, so a claim that
arrived as an archive is always the second kind. The file list is therefore
available exactly when the reader already knows what they changed, and absent
exactly when they do not.

Two agents disagreed here — one saw the file list on its own packed claim and
called the quickstart wrong, the other tested a received claim and called the
promise false. Both were right about their own case; neither could see the
rule.

`ret status --all` prints "see `ret verify` for the moved files", which is a
promise the tool cannot keep in the receiving case.

### 3. `status` advises a command that cannot succeed

On a claim with no implementation present, `ret status` ends with
`next  earn it here: ret audit .`. That audit must fail, because the gate has
nothing to judge. The right advice is to regrow first. `how-do-i.md` already
says so; `status` does not.

Related: the per-file ledger's `fixed check.sh (+ 4 more inputs)` line is
identical before and after a tamper, but sits beside `identity broken` where
it reads as a diagnostic. One agent inferred the culprit from it, then
disproved its own inference.

### 4. `ret help -a` prints an empty section

The heading "Accepted older spellings (aliases; the fourteen are the
grammar)" is followed immediately by "Plumbing". No aliases are listed, so
there is no way from the shipped help to learn which of `-o` and `--into` is
current — a question two agents hit independently, as the manual uses both.

### 5. `verify`'s help overstates its output

The `OUTPUT` block promises `fresh <root>` on success. Run non-interactively
it prints nothing, which is correct per the silence rule but not what the
help says. One agent fell back to the exit code and recorded the mismatch.

### 6. `RETICULI_DRY_PROMPT=1` — reported, not reproduced

Agent 3 reports it printed no prompt for any of the four shipped producers,
and that with `--producer codex` it performed a real billed rebuild
(`tokens=65547`). Its proposed mechanism is that the variable is not on the
environment-scrub allowlist and so cannot reach the producer. **Not
reproduced here**, because reproducing it spends money. Treated as an open
report rather than a confirmed defect.

## Defects in the manual, fixed in this change

| what | where |
|---|---|
| "`ret verify` names the moved files" stated unconditionally | `receiving.md`, `how-do-i.md` |
| `ret crosscheck . ../m3` shown with `# silent exit 0` | `make-a-claim.md` §7, `how-do-i.md` |
| M1's procedure given as "verify in place at origin"; crosscheck audits it | `process.md` §4 |
| no statement that a received, implementation-less claim has no M1 leg | `process.md` §4 |
| `assess` taught as a command, with no guidance on reading the per-kind breakdown over the aggregate, or on `not applicable` | `how-do-i.md` |
| no documented path for an agent driving `ret` directly (`--agent generic` + `ret hook`) | `how-do-i.md` |
| `examples/make` pins `wordcount.c`, so rebuilding it demonstrates compilation rather than re-derivation — nowhere stated | `how-do-i.md` |
| "every environment variable the tool reads" omits the producer-contract set | `how-do-i.md` |

## What the method is worth

Reading the manual found nothing. Executing its commands by hand found three
broken recipes. Handing it to a population that had to *accomplish something*
found a product bug, a false promise the tool itself repeats, and a set of
gaps where the manual teaches an instrument without teaching how to read it.

The cost was five agents and about ten minutes of wall clock.

The obvious next step is to stop relying on this being run by hand: the
quickstart is generated from captured runs and was the only page with no
defects in it, which is an argument for generating more of the manual the
same way.

---

# Round two

*Same day. Five fresh agents against the fixed manual: three on ground round
one covered, two on ground it never touched. All five completed their task.*

## The regressions held

The regrow-and-prove task was round one's worst, with nine false statements
and no accepting verdict through any documented path. In round two the same
task reported **"wrong in the manual: none found"** and reached
`verdict = "accept"`. The agent hit the same export exec-bit rejection,
diagnosed it the same way, then found `how-do-i.md` documenting it verbatim
with the `cp -a` workaround.

The agent handed a *transported* tampered claim quoted the corrected text
back, accepted that the tool cannot name the file, and went to the diff
fallback. Round one's agent on that ground had been misled by the old
unconditional promise.

## New defects in the tool

### 7. `ret pull` also drops the executable bit

The same defect as export/import, at a second site. Reproduced: a dependency
binary is `-rwxr-xr-x` in its own claim and `-rw-r--r--` after `ret pull`
materializes it, so a consumer's gate must `chmod +x` before running it.

Two sites makes this a property of how the tool copies files rather than a
quirk of one verb, and a candidate for one fix plus a criterion.

### 8. A refused composition walk leaves the drawer ahead of the link

After `ret pull` (no arguments) refuses at a layer, the inner drawer copy may
already have advanced to the dependency's new root while the outer link still
records the old one. `status --tree` then shows `(missing from the registry)`
and `audit` reports the layer `unresolved`. The tools surface it rather than
hiding it, but `ret help pull`'s "never moves a root; refuses where it would"
reads as though nothing moved.

### 9. `pull`'s text and `--json` disagree

For one successful component-root update, the text said `refreshed consumer`
while `--json` reported `"action": "held"` and `refreshed_count: 0`.

### 10. `--input` silently keeps only the last of repeated flags

Found during reproduction, not by an agent. `--input a --input b` seals a
claim pinning only `b`. It verifies perfectly and fails its first cold audit
with `a: No such file or directory`. The flag takes several values at once
(`--input a b`); repeating it is silent data loss at authoring time.

## Defects in the manual, fixed

| what | where |
|---|---|
| `process.md` prescribed "rebuild twice, copy, crosscheck" without warning the two-argument form breaks on executables | `process.md` §4 |
| the quickstart claimed "different bytes, same identity" over a claim whose C source is pinned | `docs/transcribe.py` |
| the generic-harness JSON contract was described but never shown, so an agent took `--generated` and skipped observation without noticing | `capturing.md` |
| diffing against a known-good copy was named as the fallback but never shown | `how-do-i.md` |
| **the three-line reusable CI workflow existed only in README.md**, so a manual reader hand-built a 77-line job from prose | `github.md` |
| nothing said what to commit; verdict files are declared, and `verify` refuses without them | `github.md` |
| **composition had no page at all** — `pack --component` appeared only as a bare item in a flag list | new `composition.md` |

## What the second round cost and bought

Five agents, about thirteen minutes of wall clock. It confirmed six fixes
held, found a second site of a known tool bug, two new tool defects, and one
whole missing capability page.

Two method notes. One agent reported "completed, zero defects" while taking
the `--generated` shortcut and thereby failing the task it was set — a
self-reported pass is not a measurement. And sibling working directories were
mutually visible, so one agent found a known-good reference next door that a
real reader would have had to source; isolate them next time.
