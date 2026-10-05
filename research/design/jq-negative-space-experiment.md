# The jq experiment: recursive specification closure on external software

*2026-10-05. Direction note and preregistration skeleton, from the
keyholder's proposal. Not normative; nothing here moves a root. The
experiment itself begins only after the reticuli→reticuli leg is
closed (bundle landed, r4 scored) and gets its own preregistration
with predictions before any room opens.*

## The claim to demonstrate

Reticuli begins with an incomplete specification, autonomously
discovers ambiguities through a population of independent
reconstructions, converts selected disagreements into specification
repairs through signed transitions, and after n generations produces
independently generated implementations whose externally observable
behavior converges — without preserving any implementation across
generations. Shown on reticuli itself and then on one substantial
external system, that is a different recursive-improvement primitive
(research/design/negative-space.md), demonstrated rather than
described.

## Why jq

- Substantial but compact boundary: a real programming language
  (lexer, parser, evaluation semantics, generators, functions,
  modules, error behavior) behind `program × input × flags →
  output/error/exit`.
- An upstream test corpus exists to seed S_0 — and is KNOWN to
  underdetermine the language: at least one independent implementation
  passes the upstream suite while maintaining thousands of additional
  differential cases because real bugs lived outside it (jq-jit's
  README). The premise — the official boundary is incomplete,
  measurably — is prior art.
- **Nature already ran the control experiment.** gojq, jaq, jqjq are
  independent human reconstructions that document where they diverge
  from jq (integer precision, key ordering, regex semantics, dates,
  undocumented behaviors, CLI). The central hypothesis becomes a
  falsifiable prediction with existing ground truth.

## The validation twist, stated as a measurement

Let H = the documented human divergences (gojq/jaq/jqjq compatibility
notes, frozen at experiment start). Let M = the divergences reticuli's
sampled reconstructions surface. Report:

    recall    |M ∩ H| / |H|     — does sampled silence find where
                                   human teams actually disagreed?
    precision  fraction of M confirmed real — by membership in H, or
               by a generated counterexample on which reference jq and
               a human implementation disagree in fact

A NOVEL confirmed divergence (in M, not in H, witnessed by a
counterexample against the human implementations) is the strongest
form of the result: a discovery the dataset did not contain.

## The contamination confound — and why it inverts the readout

jq's source, gojq's, and jaq's are in every generator's training set.
A "blind" jq rebuild is partially reconstruction from memory, not from
specification. Consequences, committed to in advance:

- **Convergence is uninformative here.** Worse than the measured
  shared-prior case (rebuild-codex-2026-09-22-quirkcalc-shared-prior):
  the prior contains the reference itself. No convergence claim will
  be made.
- **Divergence is strengthened.** An ambiguity that survives even
  shared memory of one resolution is underdetermination of the
  strongest kind. The experiment is divergence-only by design.
- **A testable side prediction:** sampled silence should
  over-concentrate on the regions the human divergence docs name —
  the ambiguities memorization cannot settle.

## Design commitments

1. **Semantics, not source.** Reconstructions in any language; the
   equivalence class is the behavioral boundary. (This is also what
   admits gojq and jaq as points in I(S).) A Python jq is a valid and
   cheap sample.
2. **Layered like the chain.** lexer → parser → core evaluation →
   builtins → CLI/IO, each layer gated by its slice of the corpus;
   per-layer silence maps locate WHICH stratum of the semantics is
   underdetermined.
3. **Pilot on the evaluation core.** S_0 = a frozen jq-1.7.x corpus
   slice covering expression semantics; regex/dates/CLI (the
   divergence-rich, platform-entangled zones) enter in later
   generations where the ground truth is richest.
4. **The oracle stays outside S.** The reference jq binary and the
   human implementations adjudicate which divergences become pins;
   they are never criteria. Every S_t → S_{t+1} is a signed root move
   with its witness recorded — the paper's artifact is a replayable
   chain of specification repairs, not only a graph.
5. **Fresh same-cardinality samples per generation**, destroyed after
   measurement, per the house method.

## The killer graph, preregistered shape

Cross-implementation semantic disagreement vs generation — annotated
with pins per step. Expected shape: STEPWISE, flat within a
generation, dropping by roughly the number of seams pinned between
generations (the no-halo result, rebuild-2026-10-03-succession-r3.md,
generalized). A smooth monotone decline would be evidence of generator
drift (priors converging on each other), not specification closure,
and is preregistered as a FAILURE signature, not a success.

## The progression

1. reticuli → reticuli (in progress: the chain, the succession runs,
   r4, cross-judging)
2. jq (this experiment — first external demonstration)
3. Lua against its official conformance repository (a general-purpose
   language: closures, coroutines, GC)
4. SQLite — the eventual monster, NOT started early; its hand-built
   testing story is the comparison point for what manual specification
   closure costs, which is the economic argument of the whole program.

## What this does not claim

- No claim that generated convergence evidences constraint (see the
  confound).
- No claim of jq reproduction as such — reproduction is the
  uninteresting diagonal of the experiment.
- No claim that the discovered silence is exhaustive: the aperture is
  the generators' priors (negative-space.md, "two grounds"); the human
  implementations are a third beam angle, which is precisely their
  value.

## Costs and sequencing

Producer-hours dominate (the thermodynamics record prices regrowth at
~300× verification). The pilot should fit the existing envelope
discipline: declared ceiling per generation, codex as the un-metered
producer when quota allows, the succession harness generalized rather
than rebuilt. Begins after: the authoring-and-sandbox bundle is
landed, r4 resumes and is scored (P1–P11), and the jq preregistration
— predictions before any room opens — is signed like everything else.
