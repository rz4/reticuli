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

> **[FINDINGS.md](FINDINGS.md) is the result.** Four runs, 23 real
> submissions, and the failure case this was built to count did not occur
> once. That null localises where the risk actually is, and the eight
> instrument defects found on the way are the concrete contribution. Read it
> first; this file is the design and the method.

## The two numbers

For each task the study measures two things in deliberately unrelated ways.

**x — what self-verification claims.** The mutation score of the model's tests
against the model's code: inject a fault into the implementation, re-run the
suite, and see whether it notices. Everything here is the model's own — the
artifact, the oracle, and the agreement between them.

**y — whether the code works.** Agreement with an oracle the model never saw:
a held-back reference implementation over ~1000 generated inputs for EvalPlus,
or the contest's own ~42 hidden cases for LiveCodeBench.

The cell that matters is **high x with low y**: a suite that looks thorough
over code that is wrong. Mutation testing is *structurally* unable to detect
it. Mutating an implementation can only ever measure agreement between code
and tests; when both encode the same misreading of the specification, they
agree perfectly and the misreading is invisible. That is the failure mode
peculiar to one process writing both halves, and it is why y has to come from
outside.

## Two corpora, because the first one could not answer the question

**`--corpus evalplus`** — HumanEval+, 164 small self-contained functions. This
is where the study started and where it ran aground: the pilots below scored
8 of 8 for two different models, so the correctness axis had no variance to
correlate anything against.

**`--corpus lcb`** (the default) — LiveCodeBench v6: 175 contest problems from
January to April 2025, of which the 63 with a `class Solution` signature are
used here. Median 42 hidden test cases per problem against HumanEval's 7, and
80 of the 175 are rated hard.

The reason for the move is not sample size. It is that **a HumanEval docstring
illustrates the awkward cases and a contest statement does not.** A model
writes its tests from the examples it is shown; when those examples cover the
failure regions, the suite covers them too and so does the code. A contest
problem gives two or three samples and hides forty cases chosen by a problem
setter whose job was to break wrong submissions — so the samples are precisely
not where the failures are, which is what real specifications look like.

Truth is computed for EvalPlus and stored for LiveCodeBench, and the reversal
is deliberate. The EvalPlus oracle runs a reference implementation because
HumanEval's own stored tests are too weak to be truth. That objection does not
carry to a contest judge's data: those are the cases a submission had to pass
to be accepted, written to break wrong answers rather than illustrate right
ones — and LiveCodeBench ships no reference implementation to run anyway.

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

**Task size and kind.** EvalPlus tasks are small self-contained functions;
LiveCodeBench tasks are competitive-programming problems. Neither is
application code, and nothing here generalises to a large codebase without
argument. LiveCodeBench in particular buys difficulty at the price of
narrowness: algorithmic puzzles are not what most agent-written code is.

**Whether the spec does the hard part.** This is what sank the EvalPlus runs
and what drove the move to LiveCodeBench. A HumanEval docstring illustrates
the behaviour with three or four cases, *including the awkward ones*. A model
writes its tests from those examples, so the suite covers exactly the regions
the spec illustrates — and the code is right in those regions too, for the same
reason. The pilot shows the mechanism directly: the one real bug either model
produced was in `multiply` over negative inputs, and the spec's own examples
include a negative input, so the tests covered it and caught the bug. That is
self-verification working *because the specification did the hard part*.
Contest statements do not, which is the point of the second corpus — but a
contest statement still shows two or three samples, so this threat is reduced
rather than eliminated.

**Contamination, again, for LiveCodeBench.** These problems are dated January
to April 2025. That postdates HumanEval by nine years but does not necessarily
postdate a current model's training data, so `--after` exists to cut the set
harder. The honest headline benefit of this corpus is difficulty, not
freshness: a model fails these whether or not it has seen them.

## The control

The study also records how big each suite is, so the mutation score has
something to beat. If suite size separates the rows as well as a mutation
score does, the mutation score is an expensive way to learn something cheap,
and the report says so.

Measuring "how big" took three attempts, all corrected against real output
rather than by reasoning. Counting `assert` statements gives **zero** — models
write a harness of their own, `check(actual, expected, "empty string")`
printing PASS. Counting call sites gives **one** — the suites are
table-driven. The number now used is how many times the suite actually calls
the function under test, measured by running it against a counting proxy in a
copy of the room.

## Running it

```bash
python3 corpus.py           # download HumanEval+ (once, small)
python3 corpus_lcb.py       # download LiveCodeBench v6 (once, ~129MB)

# free: no model calls. Validates the harness against known quadrants.
python3 run.py --corpus evalplus --backend stub --n 18

# the real thing
python3 run.py --corpus lcb --backend claude --model claude-sonnet-5 --n 25
python3 analyze.py results/lcb-claude-claude-sonnet-5-25.jsonl

# a second model over the FIRST one's tasks, not a fresh draw
python3 run.py --corpus lcb --backend claude --model claude-haiku-4-5-20251001 \
        --tasks lcb/3708,lcb/3731
python3 analyze.py results/lcb-*.jsonl        # reports them side by side
```

`--after YYYY-MM-DD` cuts LiveCodeBench by contest date, which is its
contamination control. Task sets are nested (`--n 8` is the first 8 of
`--n 25`) and `--tasks` names them outright, so two models can be compared on
exactly the same problems.

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
| `corpus.py` | HumanEval+: tasks, rooms, and a differential oracle against a held-back reference |
| `corpus_lcb.py` | LiveCodeBench: contest problems, rooms, and the contest's own hidden test data |
| `author.py` | the subject: one model call producing an implementation and its tests together |
| `oracle.py` | the judging child — timeouts, stdout suppression, `Class.method` entry points, and the comparison both corpora share |
| `run.py` | seal each room as a claim, take both numbers off it, write one row per task |
| `analyze.py` | the quadrant table, the correlations, the control, an SVG scatter |

`corpus/` and `results/rooms-*` are working data and are not committed. The
result rows and reports are.

**`--backend stub` needs `--corpus evalplus`.** The harness validation builds
its submissions out of a reference solution, and LiveCodeBench ships expected
outputs without one. The run refuses rather than failing obscurely.

## The pilot, and why the corpus has to change

Eight tasks, `claude-sonnet-5`, $1.46, 28k tokens. Every one produced an
implementation and a test suite that pass together; three needed a repair turn
after their own tests caught something.

**All eight are correct.** 6,104 judged inputs, zero disagreements with the
reference. The suites ran a median of 12 cases each and scored a mean mutation
rate of 0.96.

A weaker model was then run against the identical eight tasks, on the theory
that errors would appear and give the axis some variance. `claude-haiku-4-5`,
$0.21: **also eight out of eight.** It needed fewer repair turns than sonnet
(1 of 8 against 3 of 8) and scored a slightly higher mean mutation rate (0.96
against 0.94), which at n = 8 means nothing except that the two are not far
apart.

| task | haiku x / y | sonnet x / y |
|---|---|---|
| HumanEval/23 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/28 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/39 | 0.90 / 1.000 | 0.75 / 1.000 |
| HumanEval/88 | 0.90 / 1.000 | 0.90 / 1.000 |
| HumanEval/97 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/105 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/142 | 0.95 / 1.000 | 0.95 / 1.000 |
| HumanEval/155 | 0.95 / 1.000 | 0.95 / 1.000 |

**The y axis has no variance, for either model**, so the question the study
asks cannot be answered on this material. That is a result about the corpus,
not about self-verification, and the reason is structural rather than a matter
of sample size — see "the prompts come with worked examples" above. Running
25 or 100 more of these tasks would spend money to re-establish the same zero.

It is worth being precise about what *did* happen, because it is not nothing:
on the one task where a model wrote a genuinely wrong implementation, its own
tests caught the bug and the repair turn fixed it. **The write-tests-and-repair
loop converged to correct code every time it was asked to.** For tasks whose
specification carries its own edge cases, self-verification works. Whether it
works when the specification does not is the question, and it needs a corpus
where specifications do not.

Two things in the harness were wrong before they were right. Both are kept
here because both had the same shape: an instrument defect that reads as a
finding about a model.

**The repair turns had no context.** Every backend call is independent — there
is no conversation carried between turns — and the first repair prompt said
only "your tests do not pass, here is the error, reply with both files again".
That reached a model which could no longer see the task, its own code, or the
required reply format. It cost the most interesting row either pilot produced:
`haiku` wrote `return (a % 10) * (b % 10)` for `multiply`, which is wrong for
negative inputs because `-5 % 10 == 5` in Python, and **its own test suite
caught it** — 2 of 12 cases failed. The model then could not repair the bug,
because the harness had stopped telling it what it was doing, and the row was
recorded as "never authored". A repair prompt now rebuilds the whole
situation, and an unparseable reply is saved rather than discarded.


**The oracle counted slow as wrong.** `HumanEval/39` first came out at
y = 0.917, the study's only apparent failure. It is a correct implementation:
it computes the right twelfth prime Fibonacci number and takes twelve seconds
doing it, using trial division where the reference uses Miller-Rabin, and the
oracle's two-second call limit had been folding that into the disagreement
count. A timeout is now set aside and reported on its own line. Had that one
row not been checked by hand, the study's headline would have been a false
finding drawn from a correct program.

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
