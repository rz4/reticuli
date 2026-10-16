# Zeta internals

Zeta measures where a specification is silent by probing populations of
gate-passing implementations, and stages findings for human review. It
holds no authority: the primary claim's pinned criteria reject any
dependency on it, and nothing zeta produces has force without a signature.

## Populations

A population is a set of members that earned the current root, plus
labeled non-members used as controls.

| Population | Members | A split indicates |
|---|---|---|
| reconstructions | independently regrown implementations | behavior the criteria do not determine |
| deployment | the same bytes under each declared host environment | host dependence the root does not pin |
| foreign control | independent implementations of an externally authored specification | calibration: in the home population, criteria and candidates share an author; the foreign family does not |

Membership is root-relative. On a root move, members earned against the
old root are retired: they remain records, and stop being evidence about
the current class. Rejected and retired trees are retained as probe
controls; a defect a producer actually made ranks probes better than an
invented one.

## Probes and splits

A probe issues one call to every member in a subprocess and records the
outcome: value, refusal, or crash. Outcomes are compared under a behavior
key that excludes differences the specification licenses (e.g., refusal
wording — the spec requires a reason, not specific text). A probe that
partitions the population has found undetermined behavior. Probes
producing the same partition and outcome signature are reduced to one
phenomenon with one witness before storage.

## Classification

Two independent labels per finding.

**Lane** — adoption cost:

| Lane | Condition | Cost of pinning |
|---|---|---|
| contraction | all members agree | none; records existing behavior |
| eviction | members disagree | excludes a standing member |
| repair | independent oracle contradicts all members | specification defect |

**Rung** — evidential strength:

1. sighting — one unexpected observation
2. evidence — a broken variant survives the criteria (demonstrated
   coverage gap)
3. contact — members in verified conflict
4. transfer — a silence carried in from a foreign population, with source
   population and silence named. Required because a system cannot assert
   novelty about its own vocabulary.

Lane prices the decision; rung orders the review queue.

## Coverage

Before findings are reviewed, a mutant battery runs: broken implementation
variants, each with a declared expected outcome, judged by the full
criteria set.

- Mutant killed: the criteria already pin that behavior; related pressure
  is redundant.
- Mutant survives: criterion gap.
- Positive control (a variant that must survive) killed, or baseline
  unmutated run fails: the report is refused entirely; results would be
  artifacts.

## Entries

A queued finding is packaged as a self-contained claim: probe, observed
partition, the population probed, and the classifier code that judged it.
It replays cold with no reference to zeta, its author, or the origin
machine. Consequence: probe sources need no trust, including agent
generators — nothing about origin survives into the evidence. Entries
observed against a retired root are marked stale and sort last.

## Selection

Members of the current class are measured on axes declared in advance:
total bytes (lower better), code bytes (lower), audit seconds (lower),
documentation bytes (**higher**). Output is a Pareto frontier.
Constraints:

1. Non-members never appear on the frontier (otherwise the empty program
   dominates all size axes).
2. No winner is computed. One axis runs opposite to size because
   documentation is the one quantity no gate can check and a size ranking
   would eliminate it.
3. Moving between members changes no identity and requires no signature.
   Electing one is a human act, on the record.

## Boundary

Zeta's outputs are candidates. Every candidate replays independently. The
only path from candidate to obligation is a signature
([process §6](process.md#6-evolve)). The instrument may be fast and wrong
because it cannot decide.
