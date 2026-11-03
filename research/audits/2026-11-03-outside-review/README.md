# An outside source review, reproduced

2026-11-03. An external reviewer read the public repository — kernel, CLI,
recipe, normative specs, pinned criteria, tests, changelog, research records
— and reported four findings. They were explicit about the limit of their
method: no local clone, no execution, "code-supported analyses rather than
independently reproduced runtime results."

This directory closes that gap. **All four findings reproduce.** Two of them
are confirmed defects with runnable witnesses; one is confirmed numerically
against the shipped function; one is confirmed by reading the two pinned
documents side by side, and is worse than reported.

Nothing here is fixed yet. The remediation moves the root and two of the
questions are normative rulings the keyholder owns, so this is evidence
first.

## 1. A declared tolerance that cannot be measured accepts

`research/audits/2026-11-03-outside-review/repro_tolerance_unmeasured.py`

`spec/claim-format.md` is unambiguous: "a band that could not be measured at
all (no shared unit between the two ledgers) makes the verdict **incomplete**
rather than accepted, on the standing rule that unknown evidence is not
evidence."

`crosscheck` computes `comparable = None` when the ledgers share no unit, and
rejects only on `comparable is False`. The `incomplete` list that follows
handles an unmeasured `envelope` and an unmeasured `mutation_floor` — and not
an unmeasured `tolerance`. The same rule, applied to two of three declared
obligations.

Reproduced:

    declared tolerance : 2.0
    cost.comparable    : None
    rejected           : []
    incomplete         : []
    VERDICT            : accept        <- spec requires: incomplete

The defect sits in the exact three-valued logic the project exists to
enforce: it is the one place where "nothing disproved it" must not become
"it is established." Note also where the specification came from — that
paragraph was written into `spec/claim-format.md` on 2026-10-29 by the
coverage batch, which specified the behaviour and did not implement it. The
spec moved; the kernel did not follow.

## 2. A caller can relax a tolerance the claim pinned

`repro_caller_override.py` — the reviewer flagged this as deserving its own
test; it reproduces as a verdict flip, which makes it the sharper half of
finding 1.

    M1 cost: {'calls': 100, 'seconds': 100.0}   M3 cost: {'calls': 1, ...}
    claim-declared tolerance: 1.05

    no caller band    -> band=1.05     comparable=False  verdict=reject
    caller band 10000 -> band=10000.0  comparable=True   verdict=accept

`band = tolerance` takes the caller's value first and the claim's second, so
a verifier argument silently overrides a condition that is inside the root.
`spec/claim-format.md` says in the same section that "a claim cannot loosen
the band it already published without becoming a different claim" — and a
caller can loosen it for them, without the root moving.

## 3. The excess-agreement statistic cannot separate shared convention from shared difficulty

`repro_excess_confounder.py`

`heldout.agreement()` computes `excess = observed - [pa*pb + (1-pa)(1-pb)]`
and the module documents a positive excess as meaning the producers "share
structure the claim never named — a convention, a common training corpus, a
default both reached for and the tests never excluded."

The reviewer's counterexample: producers independent *conditional on case
difficulty*, with no shared structure at all. Run against the shipped
function, 40 trials of 2000 cases:

    half the cases p=0.90, half p=0.10
      observed agreement : 0.821
      expected baseline  : 0.500
      EXCESS             : +0.321  (sd 0.010)

    control, uniform difficulty p=0.50 everywhere
      EXCESS             : +0.003  (sd 0.012)

Their closed form predicts it exactly: `E[excess] = 2·Cov_i(p_Ai, p_Bi)`,
and `2 × (0.5·(0.81+0.01) − 0.25) = 0.32`. The control isolates difficulty as
the whole cause.

The statistic is not wrong arithmetic — it measures agreement correctly. The
*interpretation* is unidentified: it attributes to hidden convention an
effect that any difficulty spread produces for free. Every real test suite
has a difficulty spread, so the bias is always present and always positive.

## 4. Two pinned normative documents disagree — in three places, not one

The reviewer reported one disagreement. Reading both pinned files side by
side, there are three:

| question | `spec/verification.md` | `spec/claim-format.md` + kernel |
|---|---|---|
| Is the band a hard condition? | always — "Valid ⇔ … ∧ the cost envelope holds" | only when the claim declares it |
| Is there a deciding default? | "**default 2.0, normative**" | undeclared is "an *observation*: reported, never deciding" |
| What range may a tolerance take? | "any value in `[1.5, 4.0)`" | validation admits any finite number ≥ 1.0, unbounded above |

The third is not reported by the reviewer and is independently checkable:
`load_recipe` validates `tolerance` as "a finite number >= 1", so a claim may
declare `tolerance = 50` which `spec/verification.md` forbids — and the
caller override in finding 2 passed `10000`, which it also forbids.

Both documents are pinned inputs of the repository's own root. They are
jointly normative and mutually contradictory, which is exactly the condition
the project's own doctrine says a conforming reimplementer must never be
left in: two readers, two defensible implementations, one root.

## What this leaves for the keyholder

Two of these are mechanical once a decision exists; two *are* decisions.

- **Mechanical:** add the missing `incomplete` branch for an unmeasured
  declared tolerance, and pin it with a conformance vector. Pin the
  held-out arithmetic so a rebuild cannot silently change what the research
  outputs mean — the reviewer's finding that `heldout.py` is `generated`,
  `tests/` is outside the boundary, and no pinned criterion exercises
  `agreement()` is confirmed: a conforming rebuild may reimplement the
  statistic freely.
- **Normative, and the keyholder's:** which tolerance semantics is the real
  one (always-hard with a deciding default, or hard-only-when-declared), and
  what authority a verifier's `tolerance` argument should have over a
  claim's — removed entirely, allowed only to tighten, or allowed with the
  override recorded in the result.

Every item that touches `crosscheck.py`'s decision logic, either spec file,
or a criterion moves the root, so they belong in one batch rather than four.
