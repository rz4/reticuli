# Predictions for succession r15 — does the steering pin unblock claude?

*2026-10-08. Root `2d10271449f3…`, FROZEN. Written before any r15 room
opens. Lineage: claude, chosen deliberately — the binding constraint on
the whole two-family bar is a single claude qualifier, and r15 asks
whether the pin earned from r14 is the last seam or merely the next.*

## Why claude again, and why now

claude has failed five times, each on a DISTINCT seam, each the
unexercised half of a symmetric contract: r10 (input globs), r12 (room
recipe form), r13 (nested staging), r14 (pack → audit_deep record
round-trip). Four of those are now pinned into the boundary; r13's was
accepted as caught by self_check. r14 was the first to reach the TOP of
the chain before refusing — the reservoir is draining one seam deeper
per draw, not refilling. r15 is the direct test: with the
pack→audit_deep contract now steered, does a fresh claude draw qualify,
or does it surface a sixth seam one level deeper still?

## What changed since r14

The boundary moved once: `pin-the-pack-audit-deep-roundtrip` landed in
authoring_check (root 0482adb5 → 2d102714, authoring layer alone). A
claim composed via `pack(component=…)` must now audit deep — pack's
component record and audit_deep's reader are one contract. Nothing else
changed; r15 is a fresh claude draw against this one-pin-stronger
boundary.

## The predictions

- **P1. Twenty layers grow**, first attempt, as every draw has.
- **P2. The authoring layer now carries the steered contract.** r15's
  regrown pack must seal a component record its own audit_deep can read.
  If claude's prior reliably writes pack's record and audit_deep's
  reader CONSISTENTLY once the fixture demands the round trip, the
  authoring layer passes and the tree assembles.
- **P3. The crux — identity.** The assembled tree re-earns REPO_OK under
  37-module substitution (the deep audit that stopped r14). Two
  outcomes:
  - **Qualifies**: the pack→audit_deep pin was the last seam; r15 is the
    FIRST claude qualifier, 1 of 3 WITH the hard family banked. The
    strongest possible outcome — the two-family bar is satisfiable.
  - **A sixth seam**: a new unexercised contract, one level deeper. The
    reservoir is deeper than five; the rate reading continues and the
    seam is staged for the keyholder (resets nothing until signed).
- **P4. Held-out tests**: 103/103 (confidence, not identity).
- **P5. Clean matrix row**, the verdict word required.
- **P6. The claude divergence signature again** — high total surface,
  low consumed (~560–640 / ~200): a repeatable family property across
  every claude draw so far.

## The honest call either way

- **r15 qualifies** → count 1 of 3 at 2d102714 with claude banked; the
  bar is reachable as structured, and codex trials finish the set.
- **r15 finds a sixth seam** → evidence the claude reservoir is genuinely
  deeper than the chain is tall at its current pinning; each pin buys one
  more layer of reach. That itself is the result: the foreign family is
  completable only by draining the reservoir pin by pin, and the arc must
  decide whether that terminates.

## Scoring

The judge (--full-gate, --tests, --bootstrap), trial.py, crosscheck via
the r15 CLI, the matrix; the deep audit captured with FULL detail this
time (the diagnostic, not the summary-only judge), so a refusal names
its check without a second 27-minute run.
