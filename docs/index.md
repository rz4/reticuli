# reticuli

## What this is for

Two situations, one problem:

- **You receive software** — a dependency, a release, a collaborator's
  tool. What, exactly, can you check? Today the honest answer is "that it
  is the bytes someone sent," plus whatever tests they chose to bundle.
- **An agent writes software for you.** It produces a plausible
  implementation faster than you can review one, and plausibility is
  precisely what makes review hard. What, exactly, did you verify before
  you merged it?

Reticuli's answer to both is the same move: treat software the way an
experimental program treats a result. The thing of record is not the
artifact, but what the artifact has been shown to satisfy, under stated
conditions, by procedures that others can repeat. The acceptance criteria,
the specification, and the build recipe are pinned and hashed into a single
identity — the **root** — and the implementation is deliberately left out:

![What is inside the identity, and what is deliberately not](figures/identity.svg)

Because the identity excludes the implementation, an implementation is
*checkable by regeneration*: an independent producer — in practice, a
coding agent — is placed in a room containing only the pinned inputs and
asked to regrow the software from the criteria alone. If what it builds
passes the same gates, the criteria carry the software. If it cannot, the
diff between what it built and what the tests demand maps exactly what the
specification forgot to say. The full test has three machines and is
described in [The process](process.md#the-three-machine-test).

Concretely, reticuli identifies software by a SHA-256 root computed over its
**acceptance criteria, its specification, and its build recipe — and
deliberately not over its implementation**. The implementation is treated as
a reproducible artifact: it can be regenerated from the acceptance criteria
alone, by an independent producer that has never seen the original, and any
candidate that passes the acceptance gate is an equally valid member of the
class the root names. Two operations maintain this identity. `verify`
recomputes the root and compares it. `audit` re-earns it: the acceptance
criteria are run cold, in an isolated environment that contains only the
inputs the claim declares, so that nothing undeclared can influence the
verdict.

A verdict here takes one of three values: accepted, rejected, or
*incomplete*. A declared condition that was not measured is reported as
incomplete, and incomplete never counts as acceptance. The distinction
between "measured and passed," "measured and failed," and "not measured" is
preserved end to end, because it is the distinction on which the integrity
of any record of evidence rests.

## Two instruments, one authority

The repository contains two cooperating systems with deliberately different
rates of change and different levels of trust.

**The primary claim** — `src/`, `criteria/`, `spec/`, and `reticuli.toml` —
is the authoritative record. Any change to what it pins alters the root,
invalidates the standing population of independently reconstructed
implementations, and takes effect only under a human signature. It is slow
by design: its pace is the pace at which obligations should change.

**Zeta** — under `zeta/` — is the exploratory instrument. It maintains
populations of implementations (independent reconstructions, the same
implementation across host environments, and a control population of
externally authored software), probes them for behavioral differences, and
classifies each finding by what adopting it would cost: a *contraction*
formalizes behavior every member already exhibits; an *eviction* would
exclude a standing member; a *repair* indicates the population as a whole
disagrees with independent evidence. Findings accumulate in a queue as
candidates. None of them carries any force until a person reviews and signs
it, and the primary claim's own criteria enforce that nothing it depends on
reaches into zeta.

The division of labor is strict: the exploratory instrument may be fast,
speculative, and wrong, because it decides nothing; the authoritative record
moves slowly, because every move it makes is a commitment. The only channel
between the two is human authorization.

## Where to go

| If you want… | Read |
|---|---|
| the full lifecycle, from authoring a claim to evolving its obligations | [The process](process.md) |
| to use coding agents without trusting their output — producers, probes, and the one rule | [Working with agents](agents.md) |
| what CI establishes, how to review PRs with machine-written code, how claims travel | [GitHub and CI](github.md) |
| to try it in ten minutes | [Quickstart](quickstart.md) |
| the whole implementation, source and explanation together | [The implementation, annotated](book/index.md) |
| who is trusted with what | [Threat model](threat-model.md) |

## The implementation, annotated

**[The book](book/index.md)** presents every module of
both systems in full — complete source in reading order, with the
explanatory material the code already carries (module introductions,
field-level notes, design rationale recorded at the point of decision)
set alongside the code it concerns.

These pages are generated from the source, not written about it. Because the
implementation is reproducible, it can be replaced wholesale by a rebuild;
prose maintained by hand would quietly fall out of date, while a rendering
of the current bytes cannot. Regenerate at any time with
`python3 docs/weave.py`.

A suggested orientation for a first reading of the core:

1. `reticuli._kernel.core` — the vocabularies: what constitutes a verdict,
   a cost, a level of confinement.
2. `reticuli._kernel.recipe` — the pinned recipe: declared inputs, build
   steps, and gates.
3. `reticuli._kernel.identity` — the root computation: what is hashed, and
   what is excluded on principle.
4. `reticuli._kernel.build` — isolated build rooms, materialization of
   declared inputs, the environment scrub, and reconstruction.
5. `reticuli._kernel.run` and `reticuli._kernel.attest` — execution, the
   ledger, and the record: the one file format intended for third parties.
6. `reticuli._kernel.crosscheck` — comparison of independent realizations,
   including re-earning any declared quality floor.
7. The command surface (`reticuli.kernel`, the CLI), and then the
   companion, for which `zeta.lib.probe` and `zeta.lib.split` are the
   natural entry points.

**The guides** — quickstart, producing, receiving, the threat model — are
the hand-written operational documentation and are included in this site.

**What is intentionally not rendered here:** the pinned inputs themselves.
The acceptance criteria and specifications — `criteria/`, `spec/`, and
zeta's own — are the identity, and the record of them is the bytes in the
repository, not any rendering. Readers evaluating what this software
promises should read those files directly.
