# Self-verification study — claude-claude-sonnet-5-8

## The run

- 8 tasks attempted, 8 produced an implementation and a test suite that pass together
- 8 of those could be measured on both axes
- 28,187 tokens, $1.46
- 3 of 8 needed at least one repair turn after its own tests failed

## Correctness, by an oracle the model never saw

- 8 of 8 agree with the reference on every input (100%)
- 0 pass the task's ORIGINAL handful of test inputs but fail the extended set — the weak-oracle effect, and the reason a stored suite is not truth here

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

