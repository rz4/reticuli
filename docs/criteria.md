# Writing criteria that carry software

Criteria are sufficient when a producer that has never seen the
implementation, given the pinned inputs and nothing else, produces a member
of the same equivalence class. How reproducible an agent's work is depends
entirely on how sufficient the criteria are. Five rules follow, each stated
with the failure mode it prevents.

## 1. Find the discriminating criterion, because it sets the price

Criteria are not uniformly hard to rebuild from. In practice most checks
are regrowable by any competent producer, and one or two divide the field
sharply, typically those demanding exact byte-level serialization derived
from prose. Neither a model's price nor its vendor predicts which side of
that divide it lands on.

To find it, run a cheap producer until it fails; the layer where it halts
is the first discriminating criterion. Then probe each candidate model
against that criterion with `--stop-after`, at a cost in cents, before
funding full runs.

This has a consequence for authoring. Demand byte-exactness only where
identity requires it, which means digests and interchange formats, and use
tolerance bands everywhere else. Byte-exact criteria raise the capability
floor; tolerance-banded criteria are rebuildable by cheaper producers.

## 2. One check, one clause

The failure mode is a probe family that builds its test documents on a base
that is itself invalid. Every probe then fails for the same undetected
reason, every implementation "passes" by refusing everything, and the
family measures nothing while reporting normally.

So each check exercises exactly one deliberate deviation from a known-good
base, and names the specification clause it exercises. A failing check must
identify the sentence that was violated. Checks that cannot are checks
whose coverage can rot without anyone noticing, and under agent iteration
it will.

## 3. Enforce obligations where the producer can act on them

The failure mode here appears in layered builds. A producer writes one
defective function mid-stack, passes that layer's local checks, builds
several more layers on top, and is refused much later by a whole-system
check at assembly. There was no signal at the point of error, and the cause
sits far from the refusal. The fix is a fixture at the layer that owns the
function, with the assembly check kept as a backstop.

An obligation enforced only at the end of the pipeline is sound but cannot
steer. Producers converge, or exhaust their attempt budgets, based on where
the signal is. Put the check where the decision is made, and keep the
global check as the second net rather than the only one.

## 4. No battery without a live positive control

Mutation coverage works by deliberately breaking an implementation in
several ways and expecting the criteria to kill each variant. One more
thing is required: at least one variant expected to survive, meaning a
change the specification licenses, such as rewording a refusal message
where the specification requires a reason rather than specific text. The
three outcomes read as follows.

- The control survives and the mutants are killed: the criteria
  discriminate.
- The control is killed: the harness condemns everything, so the kills mean
  nothing.
- There is no control and all mutants are killed: indistinguishable from a
  broken harness.

The coverage battery refuses to emit a report if the baseline fails or the
control dies.

The same rule applies to any agent evaluation. Include cases with known
outcomes on both sides, must-catch and must-pass, or a strict gate cannot
be told apart from a dead one.

## 5. Digest a series under its own content, never a global counter

The APEIRON campaign measured this one (A66). A run claim digested each
metric series over its (step, value) pairs, where `step` was a single
global, sticky counter. A declared two-row fix near the head of one series
then relabeled every later row across every series, so most digests moved
while the measurements did not, and the verdict read "near-total
divergence" for a change that inserted two identical-valued rows. The
reference data had to be fully regenerated twice, and telling the declared
fix apart from drift required a schema-aware comparator built outside the
tool.

So key a pinned series by its own content, using a stage-local index or an
event id rather than a global counter, and an insertion then costs the rows
it inserts and nothing else. Where a declared change has to cross a series
that is already pinned, declare its shape and verify it with
`reticuli.divergence` (`docs/transitions.md`, "Declaring the shape of an
expected divergence") instead of reading a flat digest mismatch by hand.

## Measuring criteria quality

Every rule above is discoverable the same way: run independent producers
against the criteria and inspect where they disagree. Criteria quality is
an empirical property, and measuring it continuously is the subject of
[zeta internals](zeta.md).
