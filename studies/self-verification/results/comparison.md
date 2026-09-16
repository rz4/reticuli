## The same tasks, model by model

8 tasks attempted by all 2 models.

| task | claude-haiku-4-5 x / y | claude-sonnet-5 x / y |
|---|---|---|
| HumanEval/23 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/28 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/39 | 0.90 / 1.000 | 0.75 / 1.000 |
| HumanEval/88 | 0.90 / 1.000 | 0.90 / 1.000 |
| HumanEval/97 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/105 | 1.00 / 1.000 | 1.00 / 1.000 |
| HumanEval/142 | 0.95 / 1.000 | 0.95 / 1.000 |
| HumanEval/155 | 0.95 / 1.000 | 0.95 / 1.000 |

- **claude-haiku-4-5-20251001**: 0 of 8 wrong
- **claude-sonnet-5**: 0 of 8 wrong
# Self-verification study — claude-haiku-4-5-20251001

## The run

- 8 tasks attempted, 8 produced an implementation and a test suite that pass together
- 8 of those could be measured on both axes
- 21,411 tokens, $0.21
- 1 of 8 needed at least one repair turn after its own tests failed

## Correctness, by an oracle the model never saw

- 8 of 8 agree with the reference on every input (100%)
- 0 pass the task's ORIGINAL handful of test inputs but fail the extended set — the weak-oracle effect, and the reason a stored suite is not used as truth here

## The headline

Rows split at x ≥ 0.80 (a suite that looks thorough) and y = 1.000 (agrees with the reference everywhere).

| | code is right | code is wrong |
|---|---|---|
| **tests look thorough** | 8 (100%) | 0 (0%) |
| tests look weak | 0 (0%) | 0 (0%) |

No row landed in the dangerous cell. With this sample size that is weak evidence of absence, not evidence of absence.

Dangerous-cell count as the bar moves — x≥0.6: 0, x≥0.7: 0, x≥0.8: 0, x≥0.9: 0, x≥1.0: 0

## Does the mutation score predict correctness?

- mutation score vs correctness: undefined (no variation)
- test-CASE count vs correctness (the control): undefined
- suites ran 10 cases at the median

Mean mutation score 0.96

## Where the suites are blind

Mean kill rate per fault kind, over every measured task. The aggregate hides this, and this is the actionable part.

| fault kind | mean kill rate | tasks |
|---|---|---|
| comparison | 0.87 | 5 |
| boolean | 0.89 | 3 |
| arithmetic | 0.93 | 5 |
| return | 0.96 | 8 |
| argument | 1.00 | 2 |
| branch | 1.00 | 4 |
| constant | 1.00 | 6 |
| string | 1.00 | 1 |

# Self-verification study — claude-sonnet-5

## The run

- 8 tasks attempted, 8 produced an implementation and a test suite that pass together
- 8 of those could be measured on both axes
- 28,187 tokens, $1.46
- 3 of 8 needed at least one repair turn after its own tests failed

## Correctness, by an oracle the model never saw

- 8 of 8 agree with the reference on every input (100%)
- 0 pass the task's ORIGINAL handful of test inputs but fail the extended set — the weak-oracle effect, and the reason a stored suite is not used as truth here

## The headline

Rows split at x ≥ 0.80 (a suite that looks thorough) and y = 1.000 (agrees with the reference everywhere).

| | code is right | code is wrong |
|---|---|---|
| **tests look thorough** | 7 (88%) | 0 (0%) |
| tests look weak | 1 (12%) | 0 (0%) |

No row landed in the dangerous cell. With this sample size that is weak evidence of absence, not evidence of absence.

Dangerous-cell count as the bar moves — x≥0.6: 0, x≥0.7: 0, x≥0.8: 0, x≥0.9: 0, x≥1.0: 0

## Does the mutation score predict correctness?

- mutation score vs correctness: undefined (no variation)
- test-CASE count vs correctness (the control): undefined
- suites ran 12 cases at the median

Mean mutation score 0.94

## Where the suites are blind

Mean kill rate per fault kind, over every measured task. The aggregate hides this, and this is the actionable part.

| fault kind | mean kill rate | tasks |
|---|---|---|
| comparison | 0.81 | 5 |
| constant | 0.89 | 6 |
| return | 0.92 | 8 |
| arithmetic | 0.95 | 5 |
| boolean | 1.00 | 2 |
| branch | 1.00 | 3 |
| string | 1.00 | 1 |

