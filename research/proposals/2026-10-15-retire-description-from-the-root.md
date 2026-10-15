# Retire the claim of description from the root; zeta describes

2026-10-15. Staged for a keyholder signature. Not landed here. An ordinary
root move for the primary claim and a re-seal of the companion; the
population retires and the closure count resets, which is why the staging
names its own precondition: **sign only after the first MAG cohort (r28-r30
and the probes) has been judged and analyzed**, so the trials this retires
have said everything they are going to say.

## The claim being removed, in one sentence

Reticuli currently promises two kinds of statement: normative ones — the
verdict, the root, the re-earned floor — and descriptive ones, the
`assess` report that measures how much a claim's tests constrain its code
and never converts the measurement into a pass. This proposal removes the
descriptive promise from the root. Reticuli judges; zeta describes; the
keyholder decides.

## Why

**The epistemics were always slightly wrong.** A claim shipping its own
strength report is the system describing itself — the same shape as a
model writing its own tests, one level up. Description of the judged thing
by an instrument outside it is strictly better evidence, and zeta is that
instrument by construction.

**The population supersedes the sample.** At N=1, "how much do these tests
constrain?" is answered by sampling random mutants — a rate with error
bars. With a reconstruction population, the same question is answered by
what actually happened. Each assess dimension now has a measured,
population-grade successor:

| assess dimension | successor, already running |
|---|---|
| mutation (sampled rate) | zeta coverage: 19 named mutants, each with an expected outcome, plus a live positive control |
| re-derivation (one blind rebuild) | thirty succession runs; sealed closure trials; the MAG capability-floor table |
| generalization (hide cases, rebuild blind) | the 135-test held-out battery, per member |
| circularity (static read of the recipe) | moves as-is; it never needed the root |

**Description is mispriced inside the root.** Every descriptive tweak — a
new axis, a better report — is a root move that retires the population and
costs a signature: the slow-loop price for fast-loop content, the exact
mispricing the companion exists to fix. And the modules are not free to
carry: `assess.py` and `heldout.py` are produce steps a blind producer
must re-derive on every succession trial. This week's runs priced that
surface in dollars and hours.

## What does NOT move

- **`mutation_floor`, whole and untouched.** The floor is normative:
  `pack.py` calls it "the floor a crosscheck holds a redo to", the
  enforcement lives in `_kernel/crosscheck.py::mutation_score`, and
  `spec/verification.md` keeps saying M3 re-earns it. The kernel keeps the
  ability to measure and enforce; zeta takes the business of reporting.
- **`reuse.py`.** It shares the measure sub-claim with assess but it is
  the verdict cache — load-bearing for audit cost, and the subject of the
  batching partner below.
- **The honesty contract — by moving, not by dying.** The three buckets
  (measured / not_measured / not_applicable; an unmeasured dimension is
  stated, never omitted) re-pin in ZETA's criteria, so the promise changes
  whose root backs it, not whether anyone backs it.
- **The direction of dependence.** Zeta already requires reticuli; losing
  a module cannot make reticuli require zeta. `boundary_check` is
  untouched.

## The surgery, named byte by byte

In the primary claim (one root move):

1. `reticuli.toml`: delete the two produce steps — `src/reticuli/assess.py`
   (line 283) and `src/reticuli/heldout.py` (line 367).
2. Delete `src/reticuli/assess.py` and `src/reticuli/heldout.py`; drop the
   measure line from `src/reticuli/__init__.py`'s layer docstring.
3. CLI surface — the verb VANISHES, no forwarding stub (keyholder's call,
   2026-10-15): remove `_handle_assess` and the assess branch and flags
   from `_cli/parser.py`, `_r_assess` from `_cli/report.py`, and the
   `assess` line from the parser's help text.
4. `_cli/views.py`: drop the residue read — the "deciding" display no
   longer shows `assess.json` (keyholder's call, same date). Claims
   carrying old residue keep it as inert bytes; nothing reads it.
5. `criteria/measure_check.py`: keep the reuse half exactly; delete the
   assess-bucket assertions.
6. `criteria/verbs_check.py`, `criteria/render_check.py`,
   `criteria/parser_check.py`: remove `_handle_assess` / `_r_assess` /
   the help-text line from the pinned seam tuples and `_DESC`.
7. `criteria/surface_check.py`: remove `assess` from the verb list, the
   `ret assess` next-step hint, and the DECIDING rung's residue
   assertions. The trust ladder's deciding rung is re-worded to point at
   the instrument's new home rather than silently shrinking.
8. `criteria/self_check.py`: the measure sub-claim becomes `reuse.py`
   alone; re-pin the moved layer digests with dated reasons.
9. `spec/layers.md`: the surface row loses `assess.py`/`heldout.py` and
   the phrase "measuring a claim's strength".
10. `scripts/selfclaim.py` and the succession harness inherit the smaller
    decomposition; the 21-layer growth becomes 19 wherever the measure
    layer carried the two modules.

In the companion (zeta re-seals; its criteria move with it):

11. `zeta/lib/describe.py`: circularity as the static read it always was;
    per-member mutation driving `kernel.mutation_score`; per-member
    held-out pass rates read from the harness. Reports carry the three
    buckets and name what they did not measure.
12. `zeta/criteria/describe_check.py`: pins the honesty contract — the
    buckets, no grade, no winner, an unmeasured dimension stated.
13. The selection lane gains `mutation_kill` as a declared higher-is-
    better axis beside `prose_bytes`, with its `measures`/`unpinned`
    fields saying it ranks constraint, not correctness.

## What signing costs

The root moves, so the population retires and the closure count returns
to zero. Three mitigations, all already in hand: the precondition above
(analyze the cohort first, so nothing unread is discarded); MAG makes
re-qualification cheap in a way that was not true when the count first
mattered (a haiku-tier run is under $2, measured); and this should be
BATCHED with `verdict-cache-in-audit.md`, staged since 2026-10-04 and
still open, so one signature costs one rebuild and the re-qualification
runs themselves get the cheaper audits.

## What this is the second of

The selection lane was the first instrument built on the premise that
characterizing members is not judging them. This is the same premise
applied to the module that was already descriptive by its own docstring —
"THE REPORT IS DESCRIPTIVE... never converts them into a pass or a
grade" — and simply housed on the wrong side of the boundary it
describes. After the move, the names mean what they say: reticuli judges,
zeta describes, the keyholder decides.
