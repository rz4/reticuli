<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

# reticuli

**Give software a name that depends on what it must do, not on how it does it.**

A **claim** is a directory holding the tests and test data that decide whether
the software is correct, a recipe saying which files are which, and an
implementation. Its **root** is a SHA-256 over the first two — the
implementation is deliberately excluded, so the root names *every program that
passes this exact check on this exact data*.

Rewrite the implementation however you like: if it still passes, the name does
not change. Change one byte of a test, and it does.

## 1. Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/rz4/reticuli
```

## 2. Verify

This repository is a claim about itself: `reticuli.toml` pins `criteria/` and
`spec/`, and declares `src/reticuli/` generated.

```bash
git clone https://github.com/rz4/reticuli && cd reticuli
ret verify .
```

Milliseconds — it recomputes the root from the bytes and compares. Now see what
it does and does not notice:

```bash
echo "# a change" >> src/reticuli/assess.py
ret verify .          # still fresh: the implementation is free

echo "# a change" >> spec/identity.md
ret verify .          # broken: a criterion changed, so the claim did
```

## 3. Audit

`verify` compares hashes. It says nothing about whether the software works.

```bash
ret audit .           # minutes, not milliseconds: every criterion, cold
```

This copies the declared files into a sandboxed workspace and **re-runs every
check there**. A recorded "it passed" is exactly the testimony this tool exists
to replace, so the verdict is earned again rather than believed.

## 4. Regrow it — do an M3

A claim is worth something when one root survives three machines: **M1** where
it was written, **M2** a byte copy proving the record travels, and **M3** an
independent rebuild from the criteria *alone*. M3 is the one that matters — if
someone else can regrow a passing implementation from your criteria, then the
criteria really do determine the software.

Nothing under `src/` is pinned, so a rebuild room holds only the recipe, the
criteria, the gate, the specs and this file — no implementation at all.

```bash
# M2 — a byte copy. Export writes a deterministic tar of the declared
# content; import extracts it and verifies the root on the way in.
ret export . ../claim.tar
ret import ../claim.tar ../m2

# M3 — regrown from the criteria alone, by anything you like
ret rebuild . --producer "<your model or script>" --into ../m3

ret crosscheck . ../m2 ../m3
```

A pass looks like this:

```
satisfied    = true
equivalence  = true      one root across all three machines
audited      = true      every verdict re-earned on its own bytes
reuse        = true      M1 and M2 share a build digest; M3 does not
independence = "unestablished: content-independence cannot be
                established from content alone"
```

- **Same root, or it is a different claim.**
- **A different build digest than M1's.** The same digest means the bytes were
  copied, and the tool reports that as reuse rather than independence.
- **Independence is declared, not proven.** Nothing in the content can show that
  a producer never saw the original.

For a bounded first attempt, regrow the kernel alone against
`criteria/kernel_check.py` — two files in the room. It has been done blind
three times, by two vendors' models: 1,483 and 895 lines landing the earlier
root `4b90feef…`, then 709 lines landing `e650b524…`, whose three-machine
proof was re-earned with the full bill on the rebuild's own ledger — 4.6M
tokens, $25.74, wall-clock measured by the kernel rather than reported by
the producer. The claim has since been revised to `82a81357…` (the recipe's
two names, the pinned envelope with a three-valued verdict, the declared
environment), and a revision orphans its predecessor's proof by design:
re-earning it against this suite is the open exercise below.

## 5. Make your own

```
your-project/
  reticuli.toml     the recipe
  gate.py           runs every criterion, writes the verdict
  criteria/         what must be true — pinned, and your identity
  src/yourpkg/      the implementation — generated, free
  tests/            ordinary tests — not pinned
```

Write the criteria first, then an implementation, then pack it. That is your
**M1**. With `reticuli.toml` in place the recipe is the declaration and the
command is bare — the gates run, then the claim seals:

```bash
ret pack your-project
```

Without a recipe yet, the flags declare one for you:

```bash
ret pack your-project \
    --generated 'src/**/*.py' \
    --input 'criteria/*.py' 'gate.py' \
    --gate 'python3 gate.py' --output OK
```

If your checks are an ordinary pytest suite, `--pytest tests` writes the
gate for you and pins the suite as inputs. If they need installed packages,
`--environment requirements.lock` names a hash-pinned dependency set the
gates run inside — pinned into the root, because dependency versions decide
what passing means (`spec/claim-format.md`).

Add CI. A clone is a byte copy, so CI doing this on someone else's machine is
**M2**'s job in the form you already have — three lines, using the reusable
workflow this repository publishes (`.github/workflows/verify.yml`):

```yaml
jobs:
  claim:
    uses: rz4/reticuli/.github/workflows/verify.yml@main
```

It verifies the root, re-earns the gates, and uploads the run's record —
one machine's results as a document (`spec/record.md`). `ret export`/`ret
import` is the explicit version when you want bytes to hand to someone.

Then ask for an **M3**: put your root in your README and invite anyone to regrow
your implementation from your criteria and open a pull request. The build digest
tells a rebuild from a copy automatically, so the invitation is safe to make to
strangers. `ret export --blind` writes the room for them — criteria, verdicts,
and the manifest naming the target root, with the implementation withheld —
and `ret record` freezes any machine's results as a signed document
(`spec/record.md`) whose verdicts were earned by running the gates, not
copied from a log.

**This repository's own invitation is standing.** The branch
`room/kernel-82a81357` is the kernel claim's blind room; regrow
`reticuli/kernel.py` from the suite alone, by any producer, and submit your
claim with your signed record by pull request — the gates are re-run here, on
your bytes, and a submission that crosschecks lands in the provenance ledger
with your record's digest and signer embedded in the proof. The rules, the
honest caveats, and the going rate are in the repository's documentation,
beside this call's own signed record.

## What this does not prove

**Not that the code is correct.** A claim is exactly as strong as its tests, and
an implementation that passes a weak check is admitted by that check, backdoor
and all. The root names an equivalence class, and a thin check defines a wide
one. This repository ships a claim that is bad on purpose to show exactly that.

**Not independence** — only byte-reuse distinguished from a rebuild. **Not what
it cannot sandbox**: checks run under macOS seatbelt or Linux bubblewrap, and
where neither exists the fact is recorded rather than faked.

`ret assess` measures how much a check actually constrains its code — fault
injection, re-derivation by a different model, held-out generalization — and
reports numbers, never grades, because the bar belongs to the claim or to its
reader. The repository's threat model states the boundaries in full and is worth
reading before trusting any output.

## More

`spec/identity.md` defines the root exactly, with a worked example;
`spec/claim-format.md` defines the recipe, the cost envelope a redo commits
to included; `spec/verification.md` defines what each verdict means;
`spec/record.md` defines the one file other programs may parse. An
implementation in any language can be held to the identity computation with
`spec/vectors/run.py` — reproduce every expected value there and you
conform. `ret -h` lists the fourteen verbs by concept; `ret help <command>`
explains one in full, and `ret help -a` includes the accepted older
spellings.

The format has moved twice, deliberately, and both moves are recorded. From
v2.0.0 the compatibility promise stands: formats are append-only, every past
format stays readable forever, and the identity computation changes only
with a format bump and an attested migration.
