# Self-verification study — stub-claude-sonnet-5-18

## The run

- 18 tasks attempted, 18 produced an implementation and a test suite that pass together
- 18 of those could be measured on both axes
- 0 of 18 needed at least one repair turn after its own tests failed

## Correctness, by an oracle the model never saw

- 11 of 18 agree with the reference on every input (61%)
- 1 pass the task's ORIGINAL handful of test inputs but fail the extended set — the weak-oracle effect, and the reason a stored suite is not used as truth here

## The headline

Rows split at x ≥ 0.80 (a suite that looks thorough) and y = 1.000 (agrees with the reference everywhere).

| | code is right | code is wrong |
|---|---|---|
| **tests look thorough** | 8 (44%) | 6 (33%) ⟵ **the dangerous cell** |
| tests look weak | 3 (17%) | 1 (6%) |

**6 of 18 (33%) are wrong code carrying a test suite that scores 0.80 or better against itself.**

  HumanEval/34, HumanEval/49, HumanEval/61, HumanEval/103, HumanEval/118, HumanEval/155

Dangerous-cell count as the bar moves — x≥0.6: 6, x≥0.7: 6, x≥0.8: 6, x≥0.9: 6, x≥1.0: 6

## Does the mutation score predict correctness?

- mutation score vs correctness: ρ = -0.47
- test-CASE count vs correctness (the control): undefined

Mean mutation score 0.88; among the implementations that are actually wrong, 0.93

## Where the suites are blind

Mean kill rate per fault kind, over every measured task. The aggregate hides this, and this is the actionable part.

| fault kind | mean kill rate | tasks |
|---|---|---|
| argument | 0.50 | 2 |
| comparison | 0.52 | 7 |
| arithmetic | 0.82 | 8 |
| branch | 0.83 | 6 |
| string | 0.85 | 8 |
| constant | 0.86 | 12 |
| return | 0.94 | 18 |
| boolean | 1.00 | 4 |

