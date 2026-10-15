# r26 refused: the claude leg does not satisfy f9b292af

2026-10-15. Root `f9b292af5f46f69472d8b371f142638d23f7ec49677d44efb2541b1a5f75e7b1`,
frozen before the run. Lineage: claude, model sonnet. **Condition 3 failed; no
trial claim seals. The closure count stays at 1 of 3.**

Predictions were committed before the run in `predictions_r26.md`. Three of
five are falsified, and the refusal is correct.

## What happened

Growth succeeded: 21 of 21 layers, 37 modules, in roughly four hours at about
eleven minutes a layer — the ~4.6× codex ratio the paper's appendix reports,
reproduced on a fresh measurement (r25 took twenty-five minutes). One retry,
on the measure layer, and the lineage ledger names the cause: `API Error:
Can't reach the API server`. Attempt 2 grew clean. No layer was ever refused
by its own criteria.

Condition 3 then failed:

```
[claude] full gate: ok=False (4.8 minutes)
gates: REPO_OK status=failed
detail: criteria/self_check.py line 531
        assert len(deep["layers"]) == len(chained) - 1
```

## The defect, measured

`registry.audit_deep` re-earns every component's verdict against the bytes the
top claim ships. Run against a freshly built chain:

| | layers reported | keeps `kernel.audit` shape |
|---|---|---|
| authored | **18** (correct: 19 chained, 18 beneath surface) | yes |
| r26-claude | **311** | **no** |

Two distinct faults in one function.

**It does not memoise.** The chain is a DAG in which every layer carries all
layers beneath it, so a walk that recurses without remembering what it has
already audited visits each ancestor once per path. Eighteen layers become 311
audits — about seventeen times the work, which is also why the gate took 4.8
minutes against codex's 1.2. The assertion's message reads "every chained
layer beneath surface is judged", and claude does judge every one; what it
fails is judging each *once*.

**It omits the top claim's own gates.** The authored implementation runs
`kernel.audit(claim)` first and composes: "gates compose, verdicts never
carry", and "the result keeps kernel.audit's shape and adds `layers`".
Claude's walks only components and returns `{"ok", "layers"}` — no `root`, no
`gates`. So its composed verdict can report `ok` while the claim's own gates
are never consulted. Confirmed by the absent `root` key, not inferred.

Either fault alone makes the tree a non-member. It is refused.

## Predictions, resolved

- **P1** 21/21 grow — **held**, one retry and it was a dropped connection.
- **P2** the finite-cost gene steers — **held**, and informatively. Claude
  wrote a validating canonicaliser and a helper it named
  `_check_finite_nonnegative` with an explicit `math.isfinite` branch. The
  gene reached it through prose in `spec/record.md`, since the layer rooms pin
  the whole spec directory, and not through a criterion: the finite assertion
  lives in a repo-level check that cannot steer at a layer.
- **P3** identity re-earns — **falsified**.
- **P4** the trial seals at count 2 of 3 — **falsified**. Count stays at 1.
- **P5** a new seam — **falsified for this run**. The boundary learned nothing
  from r26; it correctly refused a producer. The day's one new seam came from
  zeta's identity round, not from here.
- The declared **selection** prediction is moot rather than wrong: a
  non-member cannot reach the frontier, which is the guard the lane was built
  with.

## What the refusal shows, and what it does not

It shows a criterion doing its job on a defect the reconstruction's own code
reported as `ok=True`. Claude's `audit_deep` returns `ok` while skipping the
top claim's gates; only the repository's `self_check` noticed.

It does not show that two families cannot both land this boundary. One
producer failed one function on one attempt. The codex leg landed the same
root with the same spec in front of it, so nothing here says the boundary is
too sharp — and the growth itself never refused a layer, so the failure is
localised to `audit_deep` rather than diffuse.

A second claude attempt is the obvious next move, and it is cheap relative to
what has already been spent: the defect is one function, and the producer has
never been told it got that function wrong, because the only check that
notices runs at assembly.

## The gap this exposes, staged separately

`surface_check.py` is the layer-local criterion that judges `registry.py`.
Measured against claude's tree directly:

```
surface_check.py   PASSES
self_check.py      refuses
```

So the producer received no signal at layer 18 and learned of the refusal only
at assembly, four hours later, with the cause harder to attribute. That is the
third instance today of an obligation placed where it cannot steer, and the
first with a witness. Staged in
`research/proposals/2026-10-15-layer-local-audit-deep.md`.
