# The outside-review batch: three defects an external reader found, all reproduced

2026-11-03. The root moved

    b188d96bb703c2a1774dd910237f86fa2b8e32b015a02355c31d683a3e9c0611
    → 8e4e637213d045177813113a76cd071c0003b2080859e42a1b92e93c26cdd19f

An external reviewer read the public repository — kernel, CLI, recipe,
normative specs, pinned criteria, tests, changelog, research records — and
reported four findings, explicitly bounded: no local clone, no execution,
"code-supported analyses rather than independently reproduced runtime
results." Every finding reproduced. Two were worse than reported. The
witnesses are in `research/audits/2026-11-03-outside-review/` and run.

This is the strongest external pressure the project has had, and it arrived
on the acceptance boundary rather than the implementation — which is the half
that matters, because a defect in the boundary is one a conforming rebuild is
*required* to reproduce.

## What was wrong

**1. A declared `tolerance` nobody could measure reached `accept`.**
`crosscheck` sets `comparable = None` when the two ledgers share no cost
unit, and rejected only on `False`. The `incomplete` list beside it already
carried the right rule for an unmeasured `envelope` and an unmeasured
`mutation_floor` — declared but unmeasured is incomplete, because unknown
evidence is not evidence — and the branch was missing for the third declared
obligation alone. Reproduced: `verdict = accept` with
`incomplete = []`, where `spec/claim-format.md` says `incomplete`.

The defect sat in the exact three-valued logic the project exists to enforce:
the one place where "nothing disproved it" must not become "it is
established." And its provenance is uncomfortable in a useful way — that
specification paragraph was written on 2026-10-29 by the coverage batch,
which specified the behaviour and never implemented it. The spec moved; the
kernel did not follow; nothing noticed for five days.

**2. A caller could LOOSEN a band the claim pinned.** `band = tolerance` took
the verifier's argument first and the claim's second. Reproduced as a verdict
flip: a claim declaring `tolerance = 1.05` rejected, and the same comparison
with `tolerance = 10000` passed to the verifier accepted — with the root
unmoved. `spec/claim-format.md` says in that same section that a claim
"cannot loosen the band it already published without becoming a different
claim," and a caller could loosen it on the claim's behalf.

**3. The held-out excess-agreement statistic cannot mean what it claimed.**
`heldout.agreement` computes `excess = observed - [p_A p_B + (1-p_A)(1-p_B)]`
and the module documented a positive excess as evidence the producers "share
structure the claim never named." The reviewer's counterexample: producers
independent *conditional on case difficulty* share nothing, yet the
expectation of the excess is `2·Cov_i(p_Ai, p_Bi)`, which is positive
whenever cases differ in difficulty. Measured against the shipped function,
40 trials × 2000 cases, half at p=0.9 and half at p=0.1: **+0.321** (sd
0.010). Uniform difficulty: **+0.003**. Their closed form predicted +0.32.

Every real corpus has a difficulty spread, so the bias was always present and
always positive.

**4. Two pinned normative documents disagreed — in three places.** The
reviewer reported one; reading both files side by side found three.
`spec/verification.md` said the cost band is a hard acceptance condition
always ("Valid ⇔ … ∧ the cost envelope holds"), that 2.0 is a *normative*
deciding default, and that a tolerance must lie in `[1.5, 4.0)`.
`spec/claim-format.md`, the kernel, and `criteria/kernel_check.py` all said
the band is hard *only when declared*, that undeclared is an observation, and
`load_recipe` admits any finite tolerance ≥ 1 — so a claim may legally
declare `tolerance = 50`, which `verification.md` forbade. Both files are
pinned inputs of this root: jointly normative, mutually contradictory.

## The two rulings, and why they were not judgment calls

Both questions turned out to be settled by the project's own record rather
than open:

- **Which tolerance semantics is normative.** `criteria/kernel_check.py` has
  pinned "the band is HARD only when the claim DECLARED a tolerance" since
  v2.4, and `research/provenance/revision-2026-09-17.md` records "only
  declared conditions are hard" as a *ratified rule*, with the counterexample
  it preserves: the first real three-machine proof was rejected by the
  undeclared default band for exhibiting the ordinary gap between discovery
  cost and redo cost. `spec/verification.md` simply predated the
  ratification. Reconciling it is following a decision, not making one.
- **What authority a verifier's `tolerance` has.** `build.audit` already
  carries the doctrine verbatim: *"min(), never max(): a caller may tighten
  this gate's ceiling but must not raise one the claim or the host has
  already set."* The tolerance path never applied the project's own rule.
  A receiver may hold a claim to a harder standard; nobody may relax a
  condition inside the root.

## What moved

Implementation (`src/`, generated, outside every root):

- `crosscheck`: the missing `incomplete` branch; `min` of claim and caller
  bands with the claim's value never displaced; `declared_tolerance` and
  `tightened` reported beside the band so a reader can see whose number
  decided.
- `heldout`: `agreement`'s docstring stops claiming the excess evidences
  shared convention and states the confounder with its measured size; new
  `stratified_excess` computes a **difficulty-adjusted** null from the
  leave-the-pair-out producers.

The boundary (pinned; this is what moved the root):

- `spec/verification.md` — reconciled in all three places, with the
  correction recorded in place rather than silently rewritten.
- `spec/claim-format.md` — the verifier-authority rule stated normatively.
- `criteria/kernel_check.py` — an unmeasured declared band is `incomplete`
  and names the obligation; a caller's wider band does not displace the
  claim's; a caller's stricter one does and is recorded.
- `criteria/measure_check.py` — the held-out statistic is under contract at
  last: its arithmetic, the confounder as a deterministic fixture, the
  four-producer identifiability floor, and the requirement that the marginal
  and adjusted forms be distinguishable.
- `criteria/exchange_check.py` — the growth envelope, rewritten (below).
- `criteria/self_check.py` — layer roots: `crosscheck` `1c4b81d6 →
  e7493758`, `exchange` `3b4125d6 → 55b77d5b`, `measure` `3ccbc4ab →
  a6a2d967`. Nothing beneath crosscheck moved: these are verdict and
  measurement surfaces, not identity rules.

## The queued fix, taken in the same batch

The growth envelope (staged earlier the same day as
`2026-11-03-the-growth-envelope-measures-the-host.md`) measured the host
while claiming to measure the algorithm: one sample each, with the
denominator floored at `0.05s`, so a ratio over sub-second file copies
silently became an absolute wall-clock bound of `p16 ≤ 0.4s` on a shared
runner. It refused conforming implementations on busy machines and admitted
the same implementations on idle ones. Witnessed twice on macOS CI
(`t16/t8 = 9.1`, `9.0`), both clearing on re-run with no code change, while
the bound already carried 2.3× headroom over the measured band.

Now **min-of-k**: a scheduler spike can only inflate a sample, never deflate
one, so the minimum of five repetitions estimates the uncontended cost. And
when even the minimum falls below the clock's resolution the measurement is
**skipped and said to be skipped** — untimeable here means untested here,
never a pass and never a failure, the same three-valued discipline as every
other verdict. Validated against its own acceptance criterion: the envelope
holds under deliberate eight-way CPU contention, which the original form
would have failed.

## What the reviewer got that the project had not

Their framing is worth keeping verbatim, because it names the next research
direction better than the project's own notes did:

> Reticuli can measure whether an implementation satisfies a specification.
> The harder problem is measuring whether that specification — and the
> instruments evaluating it — actually captures the intended claim.

Three of the four findings are instances of exactly that: the instrument
(the verdict logic, the agreement statistic, the timing envelope) was weaker
or less identifiable than the claim it was being read as supporting. The
fourth was two normative documents disagreeing, which is the same problem one
level up.

## Not taken

Their fourth recommendation — make consumer-level reconstruction a primary
experiment using format-5 assembly claims to test whether independently valid
components stay valid when recombined — is research, not a defect, and is the
largest item on the table. It is noted here and belongs in its own campaign
rather than this batch.
