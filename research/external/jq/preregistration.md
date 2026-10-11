# Preregistration — the jq pilot (generation 1)

*2026-10-11, drafted after phase 0 and BEFORE any room opens. Per the
design (research/design/jq-negative-space-experiment.md) this document
is signed by the keyholder before the first producer call; the
predictions below are the experiment's falsifiable commitments. The
oracles (reference jq 1.8.1, gojq 0.12.19, jaq 3.1.1 — binaries and
divergence docs frozen with hashes in phase 0) stay OUTSIDE S forever:
they adjudicate, they are never criteria.*

## The pilot's scope (design commitment 3)

S_0 = the EVALUATION-CORE slice of the frozen jq-1.8.1 corpus: the
cases exercising expression semantics (paths, arithmetic, comparison,
control flow, generators, reduce/foreach, core builtins over
JSON values) — excluding regex, dates, I/O, modules, CLI flags, and the
~43 harness-artifact cases identified in phase 0. The slice is carved
and hashed before the first room opens; its carve rule is "the case
drives only the evaluator," applied mechanically by a tagger script and
reviewed once by the keyholder.

The reconstruction target: a jq-expression EVALUATOR behind the
boundary `program × JSON input → outputs/error`, in any implementation
language (semantics, not source — a Python jq is a valid sample).
Layered per the design: lexer → parser → evaluator → builtins, each
layer gated by its slice of S_0.

## The run shape (generation 1)

Fresh blind samples from BOTH families (codex un-metered first; claude
within the declared envelope), same cardinality per family, grown by
the generalized succession harness; each sample judged against S_0 and
then DIFFERENTIALLY against the three oracles on a generated probe set
(the corpus's programs mutated mechanically — new inputs, new
compositions — so the probes are not in any training set). Samples are
destroyed after measurement (design commitment 5).

## Measurements and predictions

Let H = the frozen human-divergence set (gojq/jaq README notes + the
149 phase-0 disagreement cases). Let M = the divergences the sampled
reconstructions surface against reference jq.

- **P1 (recall).** M ∩ H / H ≥ 0.3 for the evaluation-core stratum of
  H: sampled silence finds at least a third of where human teams
  actually disagreed in this stratum, in one generation.
- **P2 (concentration).** M over-concentrates on H's named regions
  (integer precision, key ordering, error wording/behavior, generator
  edge semantics) relative to a uniform spread over S_0's surface —
  the contamination side-prediction: memorization cannot settle true
  ambiguity.
- **P3 (novelty, the strong form).** At least ONE confirmed divergence
  in M \ H: witnessed by a generated counterexample on which reference
  jq and at least one human implementation disagree IN FACT. (A
  discovery the dataset did not contain.)
- **P4 (the readout discipline).** NO convergence claim will be made —
  convergence is uninformative under contamination (the prior contains
  the reference). The experiment is divergence-only.
- **P5 (the curve's shape, for later generations).** When pins from
  generation 1 are signed and generation 2 runs, cross-implementation
  disagreement drops STEPWISE (flat within a generation, dropping by
  roughly the pins landed between). A smooth monotone decline is
  preregistered as a FAILURE signature (generator drift, not
  specification closure).

## Envelope

Generation 1 ceiling: codex un-metered via the local path; claude
capped by the keyholder's standing authorization; wall-clock bounded by
the existing gate discipline. Every S_t → S_{t+1} is a signed root move
in the jq claim's own chain, witness recorded — the artifact is a
replayable chain of specification repairs.

## Signature

Keyholder: SIGNED (rzamora, in session) — 2026-10-11. Rooms may open.
