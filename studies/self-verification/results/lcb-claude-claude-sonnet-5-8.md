# Self-verification study — lcb-claude-claude-sonnet-5-8

## The run

- 7 tasks attempted, 7 produced an implementation and a test suite that pass together
- 7 of those could be measured on both axes
- 287,316 tokens, $7.37
- 3 of 7 needed at least one repair turn after its own tests failed

## Correctness, by an oracle the model never saw

- 7 of 7 agree with the reference on every input (100%)
- **0 pass every sample printed in the problem statement and still fail the contest's hidden cases.** That gap is the room a fitted test suite lives in
- by rating: hard 7/7 correct

## The headline

Rows split at x ≥ 0.80 (a suite that looks thorough) and y = 1.000 (agrees with the reference everywhere).

| | code is right | code is wrong |
|---|---|---|
| **tests look thorough** | 4 (57%) | 0 (0%) |
| tests look weak | 3 (43%) | 0 (0%) |

No row landed in the dangerous cell. With this sample size that is weak evidence of absence, not evidence of absence.

Dangerous-cell count as the bar moves — x≥0.6: 0, x≥0.7: 0, x≥0.8: 0, x≥0.9: 0, x≥1.0: 0

## Does the mutation score predict correctness?

- mutation score vs correctness: undefined (no variation)
- test-CASE count vs correctness (the control): undefined
- suites ran 246 cases at the median

Mean mutation score 0.81

## Where the suites are blind

Mean kill rate per fault kind, over every measured task. The aggregate hides this, and this is the actionable part.

| fault kind | mean kill rate | tasks |
|---|---|---|
| branch | 0.71 | 7 |
| argument | 0.74 | 7 |
| constant | 0.74 | 7 |
| boolean | 0.75 | 4 |
| comparison | 0.87 | 7 |
| return | 0.90 | 7 |
| arithmetic | 0.93 | 7 |
| string | 1.00 | 2 |

