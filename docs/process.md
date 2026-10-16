# The process

## Design

Two situations share one failure mode:

1. Software is received. The recipient can check that the bytes match a
   hash; nothing else is checkable without trusting the sender's test
   selection and execution.
2. Software is written by a coding agent. Output volume exceeds review
   capacity, and "it passed the tests" is unverifiable if the agent could
   influence the tests, the environment, or the reported result.

Reticuli's mechanism for both: pin the obligations, hash them into the
identity, and make every verdict reproducible by a party that trusts no
one. The artifact is not the unit of trust; the obligations are.

![Root contents: criteria, spec, recipe inside; implementation, tests, docs outside](figures/identity.svg)

Because the implementation is outside the identity, it is checkable by
regeneration: a producer in an isolated directory, holding only the pinned
inputs, regrows the implementation from the criteria. If the result passes
the same gates, the criteria carry the software; if not, the diff between
what was built and what the tests demand locates the under-specification.

## Lifecycle

One claim passes through six stages: author, seal, reconstruct, judge,
record, evolve. Stages 1–5 hold the identity fixed. Stage 6 is the only
way it moves.

![Two loops: implementations cycle inside a fixed identity; obligations change only by signature](figures/two-loops.svg)

## 1. Author

A claim directory contains:

| Material | Standing | Contents |
|---|---|---|
| `criteria/` | pinned | executable acceptance checks |
| `spec/` | pinned | specification prose and conformance vectors |
| `reticuli.toml` | pinned | declared inputs, build steps, gates |
| implementation | generated | satisfies the above; defines nothing |

`ret init` creates a workspace; `ret run` records observed commands;
`ret pack` writes the recipe.

Placement rule: material that must bind a future implementer goes in
criteria or specification. Material that merely helped the current
implementer stays out.

## 2. Seal

The root is SHA-256 over the pinned material. Properties:

- Rewriting the implementation does not change the root.
- Changing any pinned byte changes the root.

`ret verify` recomputes and compares. Cost: seconds. Runs in CI on every
push.

## 3. Reconstruct

`ret rebuild` materializes the claim into a **room**: a directory
containing only the declared inputs. The process environment is scrubbed;
credentials and model selection enter only if the operator passes them
explicitly. A **producer** — any program; in practice usually a coding
agent — writes the generated outputs. The producer may read the room,
write candidates, and run the gate repeatedly. It cannot affect the
judgment stages below.

Producer guidance (hints) is excluded from the root and from acceptance. A
rebuild that requires the hint to pass measures the hint, not the
criteria.

## 4. Judge: the three-machine test {#the-three-machine-test}

Validity decomposes into three questions answered on three machines:

![Three machines: origin, transfer, blind rebuild](figures/three-machines.svg)

| Machine | Procedure | A pass establishes |
|---|---|---|
| M1 | verify in place at origin | the claim was earned where it was made |
| M2 | export, import elsewhere, verify from received bytes | transfer integrity; no corruption or substitution |
| M3 | producer sees only pinned inputs; regrows the implementation; gates re-run | the specification alone carries the software |

**Valid ⇔ one root on all three machines ∧ every gate re-earned ∧ M3's
measured cost within the declared band of M1's.** The cost band exists so
that "reproducible" cannot be satisfied by an infeasibly expensive
reproduction. Where the claim declares a mutation floor, M3 re-earns that
too.

Failure isolation:

- M1 fails: the claim never held.
- M2 fails: transfer or tamper problem; not the software.
- M3 fails: the claim is under-specified. The diff between M3's output and
  the test demands locates the missing specification. This output is used
  in stage 6.

Command mapping, by increasing strength and cost:

- `ret verify` — root comparison only.
- `ret audit` — every gate re-earned cold in a fresh room from declared
  inputs. The receiving party's tool.
- `ret crosscheck` — the full three-machine test, including the blind
  rebuild and any declared floors.

Verdicts are three-valued: `accept`, `reject`, `incomplete`. A declared
condition that was not measured yields `incomplete`. `incomplete` never
accepts. The three states are preserved end to end.

## 5. Record

`ret record` writes one machine's results — identity, gate verdicts,
environment, measured cost — in a canonical byte format. Records from
different machines are directly comparable. `ret sign` attaches a
signature; signed records are the transport for verdicts between parties.

Cost units form a ladder: `usd > tokens > calls > seconds`. Comparisons
use the strongest unit both sides measured. A cost value must be a finite
non-negative number; anything else is refused at validation.

## 6. Evolve

Stages 1–5 hold obligations fixed. Changes to obligations go through the
following pipeline, implemented by zeta ([internals](zeta.md)):

1. **Populations.** Sets of implementations that pass the current gate:
   independent reconstructions, the same bytes across declared host
   environments, and externally authored controls.
2. **Pressure.** Probes run against every member. A probe that partitions
   the population has found behavior the root does not determine.
3. **Classification.** Each finding is labeled by adoption cost:
   `contraction` (all members agree; pinning evicts no one), `eviction`
   (members disagree; pinning excludes a member), `repair` (independent
   evidence contradicts all members).
4. **Queue.** Findings wait, packaged for independent replay.
5. **Signature.** A human reviews and signs. The signature amends pinned
   material; the root moves; the standing population is retired.
   Membership is never inherited across a root move; implementations
   re-qualify against the new identity.

No agent, instrument, or finding has force without step 5.
