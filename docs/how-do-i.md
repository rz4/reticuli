# How do I…?

The common jobs, each with the command that does it and the page that
explains it. If you know what you want to accomplish and not what it is
called here, start on this page.

## Check something

**…check that a claim someone sent me is intact?**

```console
$ ret verify theirclaim
```

A hash comparison. It executes nothing and answers only "are these the bytes
they sealed?" Silent exit 0 means yes. → [Receiving a claim](receiving.md)

**…check that it actually works, on my machine?**

```console
$ ret audit theirclaim
```

Re-runs every gate cold in a sandbox, trusting no stored result. This is the
one that means something. → [Receiving a claim](receiving.md)

A claim can verify and still fail to audit, and one case surprises people:
**a claim travels without its implementation**, because the root never
covered it. Audit a blind export, or the shipped `examples/make` as it sits
in the repository, and the gate has nothing to judge — `failed — gate OK
(failed)` is the correct answer, not a broken claim. Regrow the
implementation first with `ret rebuild`. →
[Quickstart](quickstart.md#a-claim-travels-without-its-implementation)

**…see what I am trusting, in one screen?**

```console
$ ret status theirclaim          # the account
$ ret status theirclaim --all    # plus the per-file ledger
```

→ [Receiving a claim](receiving.md#reading-the-output)

**…find out whether the tests are any good?**

```console
$ ret assess theirclaim --mutants 10 -v
```

Injects faults and reports how many the tests caught. A survivor is the
actionable part: it names a behaviour nothing checks.

**Read the per-kind breakdown under `-v`, not the headline.** An aggregate of
`0.77` smooths over the thing you need: `constant: 0.33` means two of three
boundary constants can move by one without any test noticing, which is a
specific hole you can close with a specific test. A kind at `1.00` is
genuinely done. Note also that some kinds report `not applicable` rather than
a number — a claim whose only generated output is a compiled binary has no
source for the fault injector to read, and `--mutants N` is accepted and
ignored in that case. → [Writing criteria](criteria.md)

**…check who vouched for it?**

```console
$ ret sign theirclaim --check --signers ~/.ssh/my-anchor
```

On a claim nobody signed, this is `unauthorized — no authorization verifies
against a trust anchor`, which is the honest answer rather than a failure.
Where a signature does exist but you have named no anchor, the strongest
verdict available is `intact`: the signature is self-consistent, which says a
statement was signed and not by whom. →
[Receiving a claim](receiving.md#checking-a-signature-and-what-an-anchor-buys)

## Make something

**…turn work I just did into a claim?**

```console
$ ret init                                     # before you start
$ ret run "python3 check.py && printf ok > OK" # capture the check as the gate
$ ret pack . --accept OK --generated solver.py -o ../myclaim
```

`pack` declares what it *observed*, so `--generated` names the implementation
when nothing watched it being written — which is the case for any file that
existed before `ret init`, or that an unhooked editor produced. Leave it out
in that situation and the cold gate fails with `ModuleNotFoundError`, because
the file was never declared and so never materialized. With a live agent
behind `ret init --agent claude`, the hooks see the write and the flag is
unnecessary. → [Make a claim](make-a-claim.md) ·
[Capturing work](capturing.md)

**…turn a project that already has tests into a claim?**

```console
$ ret pack . --generated 'src/*.py' --pytest tests/
```

The recipe is the declaration, the gates run, and the claim seals **in
place** only if they pass. This form takes no `-o`: `-o` belongs to the
session form, which materializes a claim somewhere new from an observed
trace. → [Make a claim](make-a-claim.md#3-pack-seal-the-session-into-a-claim)

**…record this machine's results so someone else can compare?**

```console
$ ret record . -o myclaim.record.json
```

The one file other programs are meant to parse. →
[Capturing work](capturing.md)

**…make every push re-earn the verdicts, on a machine I do not control?**

```yaml
# .github/workflows/claim.yml
jobs:
  claim:
    uses: rz4/reticuli/.github/workflows/verify.yml@main
```

Three lines gets you the M2 leg of the three-machine test. →
[GitHub and CI](github.md#wiring-your-own-claim-up)

**…know which files to commit and which to leave out?**

Commit the declared inputs, the verdict files the gates write, and
`.reticuli/manifest.json`. Leave out the generated implementation and the
rest of `.reticuli/`. The verdict files are the surprising one: `verify`
refuses if one is missing, even though nothing ran. →
[GitHub and CI](github.md#what-to-commit)

**…send a claim to someone?**

```console
$ ret export . myclaim.tar          # and they: ret import myclaim.tar ./m
```

→ [Receiving a claim](receiving.md)

## Regrow something

**…regrow the implementation from the tests alone?**

```console
$ ret rebuild . --producer openai -o ../m3
$ ret crosscheck . ../m3
```

Any program that writes the withheld files counts as a producer — a compiler,
a Makefile, a script. → [Working with agents](agents.md) ·
[Writing a producer](producers.md)

!!! warning "The two-directory form cannot carry an executable"

    Given exactly two directories, `crosscheck` materializes the byte-copy
    leg itself through export and import — and **export does not preserve the
    executable bit**. For a claim whose generated output must be executable,
    that leg then fails its audit with `Permission denied` and the whole
    crosscheck rejects, however sound the rebuild was. Until that is fixed,
    pass three directories and make the copy yourself:

    ```console
    $ cp -a ../m3 ../m3copy
    $ ret crosscheck ../m3 ../m3copy ../m3b
    ```

    Claims whose outputs are interpreted — Python, say — are unaffected.

**…do it without spending money?**

Point `--producer` at a local script. The contract is the same, and
[the manual's worked example](make-a-claim.md#7-rebuild-it-from-the-tests-alone)
does exactly this in about fifteen lines.

A caveat about the shipped `examples/make`, because it is the first thing
most people rebuild: its recipe pins `wordcount.c` as an input and declares
only the compiled binary generated. Rebuilding it with `make` therefore
demonstrates that a compiler is a producer — it does not demonstrate that the
tests determine the software, because the source was handed over. For that,
use a claim whose implementation is genuinely generated, such as the prime
solver in [Make a claim](make-a-claim.md).

**…write a claim and author it as an agent, with no editor hooks?**

```console
$ ret init --agent generic
```

That prints the event contract and accepts one JSON event per call on stdin,
so a harness that is not Claude Code — including an agent driving `ret`
directly — can still have its writes and reads observed, and `pack` will then
classify files without `--generated`. →
[Capturing work](capturing.md#what-gets-observed)

**…check that a model did not just copy the original?**

`ret crosscheck` distinguishes byte reuse from a genuine rebuild. It cannot
establish that a producer never saw the original; that is recorded as a
declaration. → [What a claim proves](threat-model.md#what-is-not-established)

## Change something

**…fix a test, now that the claim is sealed?**

Editing a pinned file moves the root, which is correct — it is a different,
usually stronger claim. What follows is a procedure, not an edit. →
[Transitions](transitions.md)

**…find out whether my change moved the root?**

```console
$ ret verify .
```

If the root moved and you did not mean it to, undo rather than reseal. →
[Transitions](transitions.md#two-kinds-of-change)

## When something goes wrong

**…my claim verifies but will not audit.**

Identity is intact and the gates do not reproduce. Usual causes: a missing
dependency, a platform difference, or a test that never really passed. An
`environment` failure is reported distinctly from a gate failure, because
nothing was proven or disproven. → [Mechanisms](mechanisms.md#furnishing)

**…`verify` says broken and I did not change anything.**

Something rewrote a pinned byte — most often a formatter or import sorter run
over the whole tree.

Whether you are told *which* file depends on the claim. One you sealed
locally reports `broken — 1 pinned file(s) changed` and names them. One that
arrived as an archive reports only `broken — expected … got …`, because
export and import do not carry the per-file ledger, and no flag recovers it —
`-v` and `--json` both report `changed: null`. In that case, diff against a
known-good copy of the same claim, ignoring the local residue:

```console
$ diff -r known-good/ arrived/ --exclude=.reticuli --exclude=OK
```

→ [What a claim proves](threat-model.md#failure-modes-worth-knowing)

**…the rebuild failed. Are my tests too weak?**

Possibly, but there are four causes consistent with that observation and
under-specification is only one. Check the producer first; it is the
likeliest and the cheapest to rule out. →
[Writing a producer](producers.md#failure)

**…a gate passes here and fails in CI.**

The claim has an undeclared dependency on something your environment supplies
and CI does not. That is the defect the audit exists to surface. →
[GitHub and CI](github.md#semantics-of-a-green-check)

**…`ret sign --check` says `unauthorized` and I signed it myself.**

Trust is relative to *your* anchor. With no `allowed_signers` file nothing is
authorized to you, which is correct rather than broken. →
[Receiving a claim](receiving.md#checking-a-signature-and-what-an-anchor-buys)

## Look something up

| | |
|---|---|
| every verb, in full | [CLI reference](cli.md) |
| what the output and exit codes mean | [CLI style contract](cli-style.md) |
| what may change between releases | [Compatibility](compatibility.md) |
| the environment variables that change the tool's behaviour | `ret help environment` |
| the `RETICULI_*` variables a **producer** is handed | [Writing a producer](producers.md#the-contract) |
| a word that is doing more work than it looks like | [Glossary](glossary.md) |

`ret help environment` covers what you set to change how `ret` behaves. The
producer-contract variables — `RETICULI_CLAIM`, `RETICULI_OUTPUT`,
`RETICULI_OUTPUTS`, `RETICULI_REQUEST`, `RETICULI_USAGE` — are passed *by* the
tool *to* a producer and are documented with the contract instead.
