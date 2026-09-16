# What this study found, including the part it did not find

The question was: **when a model writes code and also writes the tests for
that code, does the mutation score of those tests predict whether the code
actually works?**

The answer, over four runs and 23 real submissions, is that the failure case
the question was built around **did not occur once**. That is the main result,
it is a null, and most of what follows is about why it is more interesting
than it sounds.

## The runs

| run | corpus | model | n | correct | mean x | x range | median test cases | cost |
|---|---|---|---|---|---|---|---|---|
| 1 | HumanEval+ | claude-sonnet-5 | 8 | **8/8** | 0.94 | 0.75–1.00 | 12 | $1.46 |
| 2 | HumanEval+ | claude-haiku-4-5 | 8 | **8/8** | 0.96 | 0.90–1.00 | 10 | $0.21 |
| 3 | LiveCodeBench, hard only | claude-sonnet-5 | 7 | **7/7** | 0.81 | 0.70–0.95 | 246 | $7.37 |
| — | 18 synthetic submissions, for validating the harness | | 18 | 11/18 | 0.88 | 0.42–1.00 | — | $0 |

Runs 1 and 2 are the same eight tasks, so they are directly comparable.
Run 3 was stopped by the operator on its eighth task; the seven that completed
are whole, judged over 42–43 hidden cases each with no truncation and no
disagreements.

**x** is the mutation score of the model's own tests against the model's own
code. **y** is agreement with an oracle the model never saw — a held-back
reference over ~1000 generated inputs (HumanEval+), or the contest's own
hidden cases (LiveCodeBench). Every one of the 23 real submissions scored
y = 1.000.

## The null, and what it localizes

The cell the study was built to count is **high x with low y**: a test suite
that looks thorough over code that is wrong. Mutation testing cannot detect
it by construction — mutating an implementation measures agreement between
code and tests, and in that cell they agree perfectly, because both encode the
same misreading of the specification.

Nothing landed there. The first reflex was that the corpus was too easy, so
the second run used a weaker model and the third used contest problems rated
*hard*. Neither helped, and the reason is worth stating precisely:

> **Difficulty and ambiguity are different things.** A hard contest problem is
> exactly specified — formal constraints, stated bounds, defined outputs.
> There is almost nothing in it to misread. Making a task harder makes the
> *implementation* more likely to be wrong; it does not make the
> *understanding* more likely to be wrong, and the dangerous cell is a failure
> of understanding.

Every corpus tried has a precise specification. To populate that cell you need
tasks that are **underspecified** — prose requirements where two competent
engineers would build different things — which is also much closer to what
agents are actually asked to do. No public benchmark is built that way, which
is either the opportunity or the warning.

## What the runs did show

**Models self-verify better than the framing assumed.** On hard problems,
`claude-sonnet-5` repeatedly wrote a **brute-force reference implementation
and fuzzed its real solution against it** — a median of 246 executed test
cases per task, one of them 2,103, against a median of 12 on the easy corpus.
That is a serious verification strategy, arrived at unprompted; the
instruction it was given says nothing about coverage, boundaries or edge
cases.

**The write-test-repair loop converged every time it was asked to.** Three of
eight tasks in run 1, one of eight in run 2, three of seven in run 3 needed a
repair turn after the model's own tests failed against its own code. Every one
of them ended correct. The single genuinely wrong implementation observed in
the whole study — `haiku` writing `(a % 10) * (b % 10)` for a units-digit
product, which is wrong for negative inputs because `-5 % 10 == 5` in Python —
was caught by the model's own test suite, 2 of its 12 cases failing.

**A mutation score is not one number.** Widening the fault injector from
operator swaps alone to eight fault kinds barely moved any aggregate —
`examples/weak` 0.80 → 0.77, quirkcalc 0.92 → 0.80, the kernel's own claim
0.50 → 0.57 — because the added operators bring easy kills along with the hard
survivors. The breakdown is where the information is:

| fault kind | pooled kill rate, 23 submissions |
|---|---|
| argument (transposed call arguments) | 0.80 |
| boolean (`and`/`or`/`not`) | 0.85 |
| comparison (including boundary swaps) | 0.85 |
| branch (forced `if`/`while`) | 0.86 |
| constant (`n±1`, `0`) | 0.87 |
| return (dropped return value) | 0.93 |
| arithmetic | 0.94 |

On this repository's own claims the same breakdown is sharper: **the kernel's
acceptance suite kills 0 of 5 injected constants** despite being sufficient for
two different models to regrow a 1,451-line kernel from it, blind, onto the
same content hash. Every survivor in `examples/weak` is a boundary at a
threshold. **Specification sufficiency and fault detection are different
quantities**, and an aggregate rate hides which one you have.

## The part that is not a null: eight instrument defects

A measurement study is only worth its instrument, and building this one
surfaced eight defects — four of them in the shipped toolchain, four in the
study harness. They are listed because each would have produced a *confident
false statement*, and because every one was caught by looking at an individual
row rather than at an aggregate.

**In the toolchain:**

1. **The fault injector was measuring itself.** It swapped operators and
   nothing else, so `examples/weak` scored 0.80 while differing from its
   sibling implementation only in two *constants* — the one fault class it was
   structurally incapable of expressing.
2. **`ret pack` wrote the gate's stdout to stdout**, where the JSON report
   lives, so `ret pack --json | jq` was broken for every claim whose gate
   prints anything — which is all of them. It also relayed only stdout, so a
   gate that *passed while warning* passed in silence.
3. **`ret assess` and `ret inspect` had no `--json`**, despite already emitting
   through that path. The measurement verb and the recipient's report were the
   two a script could not read.
4. **Mutants ran against the ten-minute gate ceiling.** A mutated loop
   condition does not terminate, so twenty mutants was three hours. Time-boxing
   each mutant against the healthy *gate's* wall time — not the audit's, which
   folds in sandbox setup — took one real task from **21 minutes to 12 seconds
   with an identical result**.

**In the study harness:**

5. **The oracle counted slow as wrong.** The only apparent failure in run 1 was
   a correct implementation that computed the right twelfth prime Fibonacci
   number in twelve seconds using trial division where the reference used
   Miller-Rabin. Unchecked, the study's headline would have been a false
   finding drawn from a correct program.
6. **Repair turns carried no context.** Each backend call is independent, and
   the repair prompt said only "your tests failed, reply with both files
   again" — reaching a model that could no longer see the task, its own code,
   or the reply format. It destroyed the single most informative row in the
   study and filed it as "the model never authored anything".
7. **The control metric was wrong twice.** Counting `assert` statements
   returns **zero** for every one of these suites, because models write a
   harness of their own. Counting call sites returns **one**, because the
   suites are table-driven. It is now a runtime count against a counting proxy.
8. **The runtime counter emitted `def Solution.method(...)`** — a syntax error —
   so every LiveCodeBench task would have silently reported "no count".

The pattern across all eight is the same, and it is the one this repository
exists to address: **something reported as established when it was not.**

## What would answer the original question

An **underspecified** corpus: tasks whose statement describes an intent without
enumerating the cases that decide it, with a hidden intended behaviour to judge
against. Nothing public is built this way, so it would have to be written.

Until then the honest summary is narrow and worth having anyway:

> For benchmark-style tasks with precise specifications, a current model's
> self-written tests are not misleading, because the code is not wrong. The
> loop catches what it can catch and repairs it. Whether that holds when the
> specification is the ambiguous part is untested — and that, not difficulty,
> is where the risk lives.

## Reproducing

```bash
python3 corpus.py && python3 corpus_lcb.py        # fetch both corpora
python3 run.py --corpus evalplus --backend stub --n 18     # free validation
python3 analyze.py results/*.jsonl
```

The stub run is the harness validating itself against known quadrants: it
places a correct implementation at y = 1.000 every time and a lookup table
that computes nothing at **x = 1.00, y = 0.001** — a perfect mutation score
over code wrong on 99.9% of its inputs. That row is the dangerous cell,
reproduced on demand. The instrument can see it. No model produced one.
