# Does a model's own test suite predict whether its code works?

A model writes a function. In the same reply it writes the tests for that
function. The tests pass.

That result is close to uninformative, and everyone shipping model-written
code knows it, but nobody has put a number on *how* uninformative. This study
is an attempt at one.

It is not part of the `reticuli` package. It is research output that uses the
package, and it lives here because the thesis the package exists to serve —
that an agent is an untrusted prover and a gate is the trust boundary — is
worth nothing without evidence about how strong such gates actually are.

## The two numbers

For each task the study measures two things in deliberately unrelated ways.

**x — what self-verification claims.** The mutation score of the model's tests
against the model's code: inject a fault into the implementation, re-run the
suite, and see whether it notices. Everything here is the model's own — the
artifact, the oracle, and the agreement between them.

**y — whether the code works.** Agreement with a held-back reference
implementation over roughly a thousand generated inputs the model never saw.

The cell that matters is **high x with low y**: a suite that looks thorough
over code that is wrong. Mutation testing is *structurally* unable to detect
it. Mutating an implementation can only ever measure agreement between code
and tests; when both encode the same misreading of the specification, they
agree perfectly and the misreading is invisible. That is the failure mode
peculiar to one process writing both halves, and it is why y has to come from
outside.

## Why the oracle is differential, not a stored test suite

The obvious oracle is a fixed set of assertions. It is a poor one. EvalPlus
showed HumanEval's own tests are weak enough to accept roughly a fifth of
solutions that are wrong, so using them as truth would compress the very axis
the study is trying to measure.

So truth here is computed rather than stored: for every input, run the
reference and the candidate and compare. Roughly a thousand inputs per task,
with the reference's `contract` deciding which inputs are part of the task at
all. A model cannot have memorised the expected values, because they are not
written down anywhere — they are produced at judging time.

## Threats to validity

Stated here rather than buried, because two of them are serious.

**Contamination.** HumanEval is old and certainly in every modern model's
training data, so a model may reproduce a memorised solution rather than solve
the task. This inflates y. It does not touch x — a model cannot memorise the
mutation score of a suite it is about to write — but it compresses the range
of y and so makes the dangerous cell *harder* to observe, not easier. A
positive finding survives this; a null finding is weakened by it.

**The competent programmer hypothesis.** Mutation testing assumes real faults
are small deviations from correct code. Model-written code often fails the
other way: a clean implementation of the wrong specification. x cannot see
that by construction. This is a limitation of the measure, and it is also part
of what the study is trying to quantify.

**Equivalent mutants.** Some injected faults do not change behaviour and
survive every possible suite, depressing x for reasons unrelated to the tests.
Recognising them in general is undecidable. Docstrings are excluded because
they are the one large, cheap source of them; the rest is noise in x.

**The prompt is the experiment.** `corpus.INSTRUCTIONS` asks for an
implementation and a test suite in ordinary words and says nothing about
boundaries, edge cases or coverage. Coaching there would raise the number
being observed. A run with a different prompt is a different experiment and
should be reported as one.

**Task size.** These are small self-contained functions. Nothing here
generalises to a large codebase without argument.

## The control

The study also counts `assert` statements in each suite. If counting asserts
separates the rows as well as a mutation score does, then the mutation score
is an expensive way to learn something cheap. The report says which, including
when the answer is unflattering.

## Running it

```bash
python3 corpus.py                                  # download the corpus (once)
python3 run.py --backend stub --n 18                # free: no model calls
python3 run.py --backend claude --model claude-sonnet-5 --n 25
python3 analyze.py results/claude-sonnet-5-25.jsonl
```

**`--backend stub` is not a model.** It fabricates submissions whose quadrant
is already known — the reference implementation, the reference with a fault
the fitted suite misses, and a lookup table that answers exactly the cases it
was shown and computes nothing. Run it first: if the harness cannot place
those three where they belong, no number it reports about a real model means
anything. On the last check it placed all of them correctly, and the lookup
table came out at **x = 1.00, y = 0.001** — a perfect mutation score over an
implementation that is wrong on 99.9% of its inputs.

**A real run spends money and quota.** The `claude` backend strips
`ANTHROPIC_API_KEY` and runs on the operator's subscription auth, so it
competes with their own usage. One call per task plus up to two repair turns.

## Files

| file | what it is |
|---|---|
| `corpus.py` | the task corpus and the room a model is given — the spec, and nothing else |
| `author.py` | the subject: one model call producing an implementation and its tests together |
| `oracle.py` | ground truth by differential execution against a held-back reference |
| `run.py` | seal each room as a claim, take both numbers off it, write one row per task |
| `analyze.py` | the quadrant table, the correlations, the control, an SVG scatter |

`corpus/` and `results/rooms-*` are working data and are not committed. The
result rows are.

## The pilot, and why the corpus has to change

Eight tasks, `claude-sonnet-5`, $1.46, 28k tokens. Every one produced an
implementation and a test suite that pass together; three needed a repair turn
after their own tests caught something.

**All eight are correct.** 6,104 judged inputs, zero disagreements with the
reference. The suites ran a median of 12 cases each and scored a mean mutation
rate of 0.96.

That is a null result, and it is a result about the *corpus*, not about
self-verification: **the y axis has no variance**, so the question the study
asks cannot be answered on this material. HumanEval is nine years old, the
tasks are small, and a current model simply does not get them wrong. This is
the contamination threat above, arriving exactly where it was predicted, and
running 25 or 100 more of these tasks would spend money to re-establish the
same zero.

The fix is not a bigger sample. It is tasks the model actually fails at, or a
model that actually fails — and running a weaker model against the same tasks
has the useful side effect of asking whether self-verification quality tracks
capability.

One number in the pilot was wrong before it was right, which is worth keeping.
`HumanEval/39` first came out at y = 0.917, the study's only apparent failure.
It is a correct implementation. It computes the right twelfth prime Fibonacci
number and takes twelve seconds doing it, because it uses trial division where
the reference uses Miller-Rabin, and the oracle's two-second call limit had
been counting *slow* as *wrong*. A timeout is now set aside and reported on its
own line rather than folded into the disagreement count. Had that not been
checked, the study's headline would have been a false finding drawn from a
correct program.

## What a run found on the way

Two defects in the toolchain surfaced here before any model was called, which
is the usual pattern: things are found when something independent exercises
them.

A mutant of a loop condition does not terminate, and the standing gate ceiling
is ten minutes — so twenty mutants of an ordinary function was three hours of
waiting for an answer available in a second. `mutation_score` now time-boxes
each mutant against how long the healthy claim takes, and reports how many
died of the clock rather than of an assertion.

And CPython invalidates a `.pyc` by mtime and size at one-second resolution,
so a harness that rewrites `impl.py` several times a second silently
re-imports the previous version whenever the new one is the same length. That
one produced a task that failed for no visible reason and passed when run by
hand.
