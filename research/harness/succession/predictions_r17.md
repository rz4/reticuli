# Predictions for succession r17 — can claude finally qualify?

*2026-10-09. Root `71fd7559e9e9…`, FROZEN, one pin past r16 (the jail
floor's seventh plank: a gate may look up the user it runs as). Lineage:
claude. The draw that asks whether the foreign family can now clear
every condition, with the sole gap r16 left — the tool-as-auditor jail —
steered into the boundary.*

## What changed since r16

One pin landed. `run_check`'s jail floor gained the user-lookup plank, so
a regrown `run.py` that writes a `(deny default)` jail too strict for a
real gate now fails the RUN LAYER's own gate during the grow — it is
steered at layer 4, long before the whole-repo audit. r16 failed EXACTLY
one scored condition (audit_repo) on exactly this; everything else it
passed (identity, 104/104 tests, the full recursive step, five of six
bootstrap steps).

## The crux has moved to the run layer

Earlier draws were steered high (authoring, the pack pin) or caught at
the top (self_check). r17's decisive moment is EARLY: layer 4, `run`. If
r17's regrown `run.py` writes a jail that permits the user-lookup (and a
real gate generally), the run layer grows and the same jail carries
through to audit_repo at the end. If it writes a too-strict jail, the
run layer's own gate now refuses it on the new plank — the steering
fires where it should.

## The predictions

- **P1. The run layer is the tell.** Either `run` grows (a sufficient
  jail — the plank steered) or `run` halts on the user-lookup plank (the
  plank bites a fresh draw, confirming it steers). Both are informative;
  a halt here is the steering pin doing its job, not a merit failure.
- **P2. authoring clears** (the pack->audit_deep pin holds, as in r14/r15/r16).
- **P3. If the run layer grows with a sufficient jail, the whole chain
  grows and IDENTITY passes** (r16 already proved claude's content
  conforms; nothing about that regressed).
- **P4. The crux this time — audit_repo.** If r17's jail permits a real
  gate, the regrown tool AS AUDITOR re-earns the repo's verdicts cold and
  bootstrap reports SUCCESSION HOLDS. That is the condition r16 missed;
  with the jail now steered, r17 should clear it.
- **P5. The rest, as r16 showed reachable:** 104/104 held-out tests, the
  recursive step (trial.py) green, a clean matrix row, the verdict word
  required.
- **P6. The claude divergence signature** (high total / low consumed).

## The honest call either way

- **r17 qualifies** → the FIRST claude qualifier: count 1 of 3 at
  71fd7559 with the binding family banked, and the two-family bar is
  demonstrably reachable. The strongest outcome of the entire arc.
- **r17 finds an eighth seam** → the reservoir is deeper still, on yet
  another surface; the draw either halts at the run layer (plank steers,
  a good sign the pin works) or surfaces something new downstream. Each
  is a measurement, not a stall.

## Scoring

Grow (watch the run layer), then the identity full gate with full detail
captured, then --tests, --bootstrap (the audit_repo condition is the one
to watch), and trial.py. Full scoring before anything is claimed.
