# Quickstart

Ten minutes, no API key, no model.

## Install

```
pip install git+https://github.com/rz4/reticuli.git
ret --help
```

Or from a clone, which is what you want if you intend to read the specs and
examples alongside:

```
git clone https://github.com/rz4/reticuli.git && cd reticuli
pip install .
```

Python 3.11 or newer, no dependencies. The repository is currently private, so
the git install needs credentials that can read it.

## 1. Verify something that already exists

```
$ ret verify examples/quirkcalc
name = "quirkcalc"
root = "03d039ca6878…"
verdict = "fresh"
```

`verify` answers one question: *do the bytes here still hash to the root this
claim was sealed at?* It does **not** re-run anything. For that:

```
$ ret audit examples/quirkcalc
verdict = "earned"
```

`audit` re-runs the claim's tests in a sandbox and requires the recorded
verdict to reproduce. The distinction matters: `verify` checks identity,
`audit` checks that the claim still *holds*. A stored "tests passed" is never
trusted.

## 2. See what the identity is made of

Open `examples/quirkcalc/claim.toml`. Three kinds of thing:

| | in the root? | |
|---|---|---|
| `inputs` | **yes** | the test script and 59 fixture files |
| `class = "generated"` | no | `calc.py`, the implementation |
| `class = "validated"` | yes | `OK`, the verdict the gate wrote |

So edit `calc.py` however you like — add comments, rewrite it entirely — and
as long as the 59 cases still pass, `ret verify` reports the same root. Change
one byte of one case file and the root changes immediately, because you
changed what is being claimed.

That is the core idea: **the identifier names the criteria, not the code.** It
denotes the set of all implementations that satisfy them.

## 3. Make a claim of your own

Take any project with a test command:

```
$ cd myproject
$ ret pack myclaim \
      --generated "src/*.py" \
      --input "tests/*.py" \
      --gate "python3 -m pytest -q tests && printf ok > OK" \
      --output OK
[pack]
name = "myclaim"
root = "257c14ff16f9…"
generated = 1
inputs = 1
```

`pack` writes a `claim.toml`, runs the gate once to be sure it passes, and
seals. Your test files are now pinned into the identity; your source is not.

## 4. Rebuild it

`rebuild` regenerates the generated outputs in a clean workspace and re-runs
the gate. The producer is any program that can do the regenerating:

```
$ ret rebuild examples/make --producer "make" --into /tmp/rebuilt
```

For [`examples/make`](../examples/make/README.md) the producer is a compiler,
and two different compiler settings land on the same root with different
binaries. For a claim whose implementation is meant to be re-derived rather
than compiled, the producer can be a language model:

```
$ ret rebuild myclaim --producer "python3 -m reticuli.producers.openai" --into /tmp/m3
```

Same verb, same verification; only the producer differs.

## 5. Ask how much the tests actually prove

If a model wrote both the code and the tests, the tests were fitted to the code
and passing them establishes very little. `assess` measures how much constraint
is really there, and reports numbers rather than a grade:

```
$ ret assess myclaim
  circularity   ok      the gate is decided by pinned files, not generated code
  mutation      0.75    3 of 4 injected faults detected; sampled 4 of 5 sites

  not measured
    re-derivation   no independent producer was asked to rebuild from the tests
    generalization  no held-out run
```

The cheap rungs run by default. The expensive one — asking a *different* model
to rebuild the implementation from the tests alone — is opt-in, because it
spends money:

```
$ ret assess myclaim --rebuild "python3 -m reticuli.producers.openai"
  re-derivation  satisfied         rebuilt from the tests alone; same root
  independence   different-vendor  claude-opus-5 -> gpt-5; declared, not established
```

That last rung is the strong one: if an independent model can reconstruct the
program from the tests, the tests are a specification rather than a net. Record
who wrote the original with `ret pack --by <model>`, or independence has
nothing to compare against.

**A failed rebuild does not by itself mean your tests are weak.** Four things
cause it — a broken producer, under-specification, a harness mismatch, or a
model that wasn't capable enough — and the report says so rather than letting
you draw the flattering conclusion.

The rung above that asks whether tests which *do* specify the software specify
it in general, or only enumerate the cases somebody happened to write. If your
claim pins a corpus of cases, `--heldout` hides a fraction of them, re-seals on
the rest, rebuilds blind from what is left, and judges each rebuild on the
cases it never saw:

```
$ ret assess examples/quirkcalc --heldout 0.3 \
      --heldout-producer "a=python3 rebuild_a.py" \
      --heldout-producer "b=python3 rebuild_b.py"
  generalization  1.00   sealed: 18 of 18 hidden cases pass … (a control)
                  0.78   a: 14 of 18 hidden cases pass, rebuilt from the 41 kept of 59
                  0.67   b: 12 of 18 hidden cases pass, rebuilt from the 41 kept of 59
                  +0.30  a vs b: agree on 0.89 of the hidden cases against 0.59
                         expected — shared structure the claim never named
```

A high rate means the retained cases carried the behaviour. A low one means
they only enumerated it. The last line is the interesting one: two producers
agreeing far more than their individual rates predict means something they both
reached for — a convention, a shared default — is doing work the claim never
named. The split is seeded from the claim's root, so it reproduces for anyone
holding the claim and cannot be re-rolled until a flattering set is hidden.

## 6. Check reproducibility across machines

```
$ ret crosscheck M1 M2 M3
satisfied = true
```

Three configurations: the original, a byte copy (does it survive transfer?),
and an independent rebuild (do the tests alone actually specify the software?).
Valid means one root across all three with every test re-executed — not
compared logs, not trusted verdicts.

## Where to go next

- [`spec/claim-format.md`](../spec/claim-format.md) — the format itself
- [`spec/identity.md`](../spec/identity.md) — exactly what the hash covers
- [`examples/tomli/`](../examples/tomli/README.md) — a claim over a real TOML
  parser, judged by an external conformance corpus, which mechanically
  detected that one shipped release no longer implements TOML 1.0.0
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the one non-obvious rule if you
  edit this repository
