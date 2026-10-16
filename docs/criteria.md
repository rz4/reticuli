# Writing criteria that carry software

Definition: criteria are **sufficient** when a producer that has never seen
the implementation, given the pinned inputs only, produces a member of the
same equivalence class. Agent reproducibility is bounded by criteria
sufficiency. Four rules follow, each stated with the failure mode it
prevents.

## 1. Locate the discriminating criterion; it sets the price

Criteria are not uniformly hard to rebuild from. In practice most checks
are regrowable by any competent producer, and one or two — typically those
demanding exact byte-level serialization derived from prose — divide the
field sharply. Neither a model's price nor its vendor predicts which side
of the divide it lands on.

Procedure: run a cheap producer to failure; the layer where it halts is
the first discriminating criterion. Probe each candidate model against
that criterion (`--stop-after`, cost in cents) before funding full runs.

Authoring consequence: demand byte-exactness only where identity requires
it (digests, interchange formats). Use tolerance bands elsewhere.
Byte-exact criteria raise the capability floor; tolerance-banded criteria
are rebuildable by cheaper producers.

## 2. One check, one clause

Failure mode: a probe family builds its test documents on a base that is
itself invalid. Every probe then fails for the same undetected reason,
every implementation "passes" by refusing everything, and the family
measures nothing while reporting normally.

Rule: each check exercises exactly one deliberate deviation from a
known-good base, and names the specification clause it exercises. A
failing check must identify the violated sentence. Checks that cannot are
checks whose coverage can rot without detection — and under agent
iteration, will.

## 3. Enforce obligations where the producer can act on them

Failure mode: in a layered build, a producer writes one defective function
mid-stack, passes that layer's local checks, builds several more layers,
and is refused much later by a whole-system check at assembly — with no
signal at the point of error, and the cause far from the refusal. Fix: a
fixture at the layer that owns the function; the assembly check retained
as backstop.

Rule: an obligation enforced only at pipeline end is sound but cannot
steer. Producers converge or exhaust attempt budgets based on where the
signal is. Place the check where the decision is made; keep the global
check as the second net, never the only one.

## 4. No battery without a live positive control

Mutation coverage: deliberately broken implementation variants, each
expected to be killed by the criteria. Required in addition: at least one
variant expected to **survive** — a change the specification licenses
(for example, rewording a refusal message, where the
specification requires a reason rather than specific text). Interpretation:

- Control survives, mutants killed: criteria discriminate.
- Control killed: the harness condemns everything; kills are meaningless.
- No control, all mutants killed: indistinguishable from a broken harness.

The coverage battery refuses to emit a report if the baseline fails
or the control dies.

Same rule for any agent evaluation: include cases with known outcomes on
both sides (must-catch, must-pass), or a strict gate cannot be
distinguished from a dead one.

## Measuring criteria quality

Each rule above is discoverable the same way: run independent producers
against the criteria and inspect disagreements. Criteria quality is an
empirical property; measuring it continuously is the subject of
[zeta internals](zeta.md).
