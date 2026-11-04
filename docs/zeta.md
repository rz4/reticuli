# Zeta internals

Zeta measures where a specification is silent, by probing populations of
gate-passing implementations and staging what it finds for human review. It
holds no authority: the primary claim's pinned criteria reject any dependency
on it, and nothing zeta produces has force without a signature.

## Populations

A population is a set of members that earned the current root, plus labeled
non-members used as controls.

| Population | Members | A split indicates |
|---|---|---|
| reconstructions | independently regrown implementations | behavior the criteria do not determine |
| deployment | the same bytes under each declared host environment | host dependence the root does not pin |
| foreign control | independent implementations of an externally authored specification | calibration: in the home population, criteria and candidates share an author; the foreign family does not |

Membership is root-relative. On a root move, members earned against the old
root are retired, meaning they remain records and stop being evidence about
the current class. Rejected and retired trees are kept as probe controls,
since a defect a producer actually made ranks probes better than an invented
one.

## Probes and splits

A probe issues one call to every member in a subprocess and records the
outcome, which is a value, a refusal, or a crash. Outcomes are compared under
a behavior key that excludes differences the specification licenses, such as
refusal wording where the spec requires a reason rather than specific text. A
probe that partitions the population has found undetermined behavior. Probes
producing the same partition and outcome signature are reduced to one
phenomenon with one witness before storage.

## Classification

Each finding carries two independent labels.

The **lane** is what adopting it would cost:

| Lane | Condition | Cost of pinning |
|---|---|---|
| contraction | all members agree | none; records existing behavior |
| eviction | members disagree | excludes a standing member |
| repair | independent oracle contradicts all members | specification defect |

The **rung** is how strong the evidence is:

1. sighting — one unexpected observation
2. evidence — a broken variant survives the criteria, which demonstrates a
   coverage gap
3. contact — members in verified conflict
4. transfer — a silence carried in from a foreign population, with the source
   population and the silence named. This rung is required because a system
   cannot assert novelty about its own vocabulary.

The lane prices the decision and the rung orders the review queue.

## Coverage

Before findings are reviewed, a mutant battery runs: broken implementation
variants, each with a declared expected outcome, judged by the full criteria
set. There are three ways to read the result.

- A mutant killed means the criteria already pin that behavior, so related
  pressure is redundant.
- A mutant that survives is a criterion gap.
- If the positive control, which is a variant that must survive, is killed,
  or the baseline unmutated run fails, the report is refused entirely,
  because its results would be artifacts.

## Entries

A queued finding is packaged as a self-contained claim holding the probe, the
observed partition, the population probed, and the classifier code that
judged it. It replays cold with no reference to zeta, its author, or the
origin machine. That is what lets probe sources go untrusted, agent
generators included: nothing about origin survives into the evidence. Entries
observed against a retired root are marked stale and sort last.

## Selection

Members of the current class are measured on axes declared in advance: total
bytes and code bytes and audit seconds, where lower is better, and
documentation bytes, where higher is. The output is a Pareto frontier, under
three constraints.

1. Non-members never appear on the frontier, since otherwise the empty
   program dominates every size axis.
2. No winner is computed. One axis runs opposite to size because
   documentation is the one quantity no gate can check, and a size ranking
   would eliminate it.
3. Moving between members changes no identity and requires no signature.
   Electing one is a human act, on the record.

## Boundary

Zeta's outputs are candidates, and every candidate replays independently. The
only path from candidate to obligation is a signature
([process §6](process.md#6-evolve)). The instrument is allowed to be fast and
wrong, because it cannot decide anything.
