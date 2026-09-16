<p align="center"><img src="docs/assets/logo.png" alt="reticuli" width="160"></p>

# reticuli

**Give software a name that depends on what it must do, not on how it does it.**

A **claim** is a directory holding three things: the tests and test data that
decide whether the software is correct, a recipe saying which files are which,
and an implementation. Its **root** is a SHA-256 over the first two — the
implementation is deliberately excluded.

So the root does not name a program. It names **every program that passes this
exact check on this exact data**. Rewrite the implementation however you like:
if it still passes, the name does not change.

```
$ ret verify .
[verify]
name = "reticuli"
phase = "sealed"
verdict = "fresh"
root = "…"
```

That is this repository checking itself. `reticuli.toml` at the root declares
`criteria/` and `spec/` as pinned and `src/reticuli/` as generated, so the
repository is a claim about itself, and the command above is an integrity check
on a fresh clone.

> **Why the root is not printed here.** This file is pinned — its bytes are
> inside that root — and a pinned file cannot contain the hash of a set it
> belongs to: writing the value in would change the file, which would change
> the value. The root lives in `.reticuli/manifest.json`, which is outside the
> claim for exactly this reason. Being pinned also makes this file the prose
> specification handed to anyone regrowing the software from its criteria, so
> it references only other pinned files and stands on its own in a rebuild
> room.

## The problem

Two of them, and they turn out to be the same problem.

**You cannot tell whether a dependency still does what it did.** A version
number is an assertion by its author. "Which releases implement TOML 1.0.0?" is
answered today by reading changelogs and hoping. It should be answered by
running the standard's own test corpus and getting a verdict with the failing
cases attached.

**You cannot tell whether generated code was verified.** When a model writes an
implementation and writes the tests for it in the same breath, the tests passing
means very little — the same process produced the artifact and its oracle.
Somebody has to hold the criteria fixed, and independent of whoever writes the
code.

Both need the same thing: **criteria that exist separately from the
implementation, and an identity computed from the criteria.**

## How it works

```
root = sha256(canonical_json({
    "digest":        "sha256",
    "recipe":        <the parsed reticuli.toml>,
    "input:<path>":  <sha256 of each pinned file>,      the criteria
    "pinned:<path>": <sha256 of each pinned output>,    the verdicts
}))
```

Generated files never enter it. `spec/identity.md` states this exactly, with a
worked example; `spec/claim-format.md` defines the recipe; `spec/verification.md`
defines what each verdict means.

Two commands do different jobs:

| | |
|---|---|
| `ret verify <claim>` | do the bytes still hash to the recorded root? Milliseconds. Says nothing about whether the software works |
| `ret audit <claim>` | copy the declared files into a sandboxed workspace and **re-run every gate there**. Never trusts a stored verdict |

That distinction is the whole design. A recorded "it passed" is exactly the
testimony this tool exists to replace, so `audit` earns the verdict again rather
than believing one.

## Try it, 30 seconds

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/rz4/reticuli

git clone https://github.com/rz4/reticuli && cd reticuli
ret verify .          # recompute the root from the bytes, compare
ret audit .           # ~22s: every criterion re-run, sandboxed
```

Then break it on purpose:

```bash
echo "# a change" >> src/reticuli/assess.py
ret verify .          # still fresh — the implementation is free

echo "# a change" >> spec/identity.md
ret verify .          # broken — a criterion changed, so the claim did
```

The same idea on software nobody here wrote: a claim over *a conforming TOML
1.0.0 parser*, judged by 709 cases from the external `toml-test` corpus. `tomli`
2.3.1 and CPython's stdlib `tomllib` are both members — swap either in and the
root is unchanged. `tomli` **2.4.1** is not: it scores 700/709, because 2.4.0
adopted TOML 1.1.0. Which releases implement the standard you depend on stops
being a changelog question. That claim is sealed in this repository, alongside
one that is deliberately *bad*, one whose producer is a compiler rather than a
model, and this repository sealed as six layered claims.

## The three-machine test

A claim is worth something when one root survives three machines:

```
 M1  the original          sealed and audited where it was written
 M2  a byte copy           the record survives transfer intact
 M3  an independent redo   regrown from the criteria ALONE, by someone else
```

M1 shows the claim was earned. M2 shows it travels. **M3 is the one that
matters**: if a second party can regrow a passing implementation from the
criteria alone, then the criteria really do determine the software.

It has been done here. `criteria/` and `spec/` were handed to two different
vendors' models, each blind to the other's work and to the original. They wrote
kernels of **1,483 and 895 lines** — no shared code, one 40% shorter than the
other — and both landed on root `4b90feef…`, each verifying records the other
had sealed.

## Do an M3

**This is the contribution the project most wants, and you can do it against the
repository you just cloned.**

Nothing under `src/` is pinned, so a rebuild room contains only the recipe, the
criteria, the gate, the specs and this file — no implementation at all. Regrow
one:

```bash
ret rebuild . --producer "<your model or script>" --into ../reticuli-m3
ret crosscheck . ../reticuli-m2 ../reticuli-m3
```

What makes a submission real, and what does not:

- **It must land on the same root.** A different root is a different claim.
- **Its build digest must differ from M1's.** The same digest means the bytes
  were copied; the tool reports that as reuse rather than independence, without
  being asked.
- **Independence is declared, not proven.** Nothing in the content can show that
  a producer never saw the original. A submission says who produced it, and that
  is recorded as a declaration rather than a fact.

For a bounded first attempt, regrow the kernel alone rather than the whole
package: its claim is sealed under `examples/kernel/`, its criterion is
`criteria/kernel_check.py`, and its rebuild room holds two files.
It has been regrown blind twice, most recently in 12 minutes for $3.40.

## What this does and does not prove

**It proves** that these criteria hold on these bytes, re-earned rather than
remembered — and, where an M3 exists, that the criteria determine the software
strongly enough for a second party to reconstruct it.

**It does not prove the code is correct.** A claim is exactly as strong as its
tests. An implementation that passes a weak check is admitted by that check,
backdoor and all: the root names an equivalence class, and a class defined by a
thin check is a wide one. `examples/weak` is a claim that is bad on purpose —
two implementations with genuinely different behaviour and the same root —
because you have no reason to trust a green result until you have watched the
tool produce a red one.

**It does not establish independence**, only distinguishes byte-reuse from a
rebuild. **It does not sandbox what it cannot**: gates run under macOS seatbelt
or Linux bubblewrap, and where no sandbox exists the fact is recorded rather
than faked. **It does not verify the producer**, only the artifact.

`ret assess` measures how much a check actually constrains its code — fault
injection, re-derivation by a different model, held-out generalization — and
reports numbers rather than grades, because the bar belongs to the claim or to
the reader. The repository's threat model states these boundaries in full and
should be read before trusting any output.

## Layout — and the shape of a project that uses reticuli

**This repository is the template.** A project using reticuli has a root that
looks like the first table; the second exists only because this project is
reticuli itself.

One rule sorts every file: *if editing it should change what the project claims
to be, the root commits to it.* Most of what the root commits to is
**criteria** — things `gate.py` executes. The rest is **context**: bytes the
claim is committed to, which nothing runs.

### The template

| path | class | what it is |
|---|---|---|
| `reticuli.toml` | *is* the recipe | what is pinned, what is generated, what gates. Its parsed content is in the root, so comments and layout are free |
| `gate.py` | **criterion** | what the recipe runs. Runs every criterion and writes the verdict |
| `criteria/` | **criteria** | all of them, with no pointers elsewhere. Most run standalone; a claim's own gate runs staged, which `gate.py` names explicitly rather than leaving to a glob |
| `README.md`, `pyproject.toml`, `docs/assets/logo.png` | **context** | what the project says it is, what it ships as, and its mark. Nothing executes these, and the root commits to them anyway — you should not be able to change the promise without changing the identity |
| `src/<package>/` | *generated* | the implementation. Free: rewrite it and the root holds |
| `tests/` | outside | ordinary tests, pytest-discoverable. Adding one changes your confidence, never the identity |
| `.github/workflows/` | outside | CI, which is the M2 leg: the same bytes re-earning their verdicts elsewhere |
| `.reticuli/manifest.json` | outside | the sealed root. It records the identity, so it cannot be inside it |

### What reticuli adds, being self-hosting

| path | class | what it is |
|---|---|---|
| `spec/` | **criteria** | the format, the identity computation, verification semantics, the layer map. A project with prose criteria worth pinning would have an equivalent; most will not |
| `scripts/selfclaim.py` | **criterion** | builds the six-layer chain of this package; `criteria/self_check.py` calls it and does the asserting |

Beyond the table, the repository also carries worked claims to read and a
documentation set — the threat model, the recipient's guide, the producer
contract, the compatibility story, and a dated provenance record of how it came
to exist. None of them is pinned, so none is named here: this file is inside the
claim, and a claim that describes itself using material it does not commit to is
one whose description can drift without its identity noticing.

The package also ships a second, independent implementation of
`spec/identity.md`, kept so the two must agree — and kept from importing the
rest of the package, or it would stop being a second one.

## Contributing

```bash
pip install -e '.[dev]'
python3 gate.py       # every criterion, exactly as CI runs it
pytest tests/         # ordinary tests
```

Editing anything the root commits to moves the root, and you re-earn it:

```bash
python3 gate.py && python3 -c "from reticuli import kernel; kernel.seal('.')"
```

The contributing guide has the rest.

## Lineage

This repository was built by its own methodology. The specification in `spec/`
was extracted from a first implementation, the v2 kernel was then regrown blind
against it, and the seed claim was sealed by the regrown kernel at a root an
independent implementation computes identically. The provenance record holds
every step, including what each rebuild got wrong.

Pre-1.0: the format has already moved twice, deliberately, and both moves are
recorded. The compatibility note says what is stable and what still moves.
