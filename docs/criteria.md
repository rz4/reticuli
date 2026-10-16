# Writing criteria that carry software

Definition: criteria are **sufficient** when a producer that has never seen
the implementation, given the pinned inputs only, produces a member of the
same equivalence class. Agent reproducibility is bounded by criteria
sufficiency. Four rules follow, each from a measured failure in this
repository's reconstruction trials.

## 1. Locate the discriminating criterion; it sets the price

Criteria are not uniformly hard to rebuild from. Measured: most layers of
this repository regrow in under a minute per layer across all tested
models; one criterion (exact byte-level serialization derived from prose)
splits the field — some models pass on the first attempt for under $0.05,
others exhaust a 3-attempt budget and 2M+ tokens without passing. Neither
price nor vendor predicts the outcome.

Procedure: run a cheap producer to failure; the layer where it halts is
the first discriminating criterion. Probe each candidate model against
that criterion (`--stop-after`, cost in cents) before funding full runs.

Authoring consequence: demand byte-exactness only where identity requires
it (digests, interchange formats). Use tolerance bands elsewhere.
Byte-exact criteria raise the capability floor; tolerance-banded criteria
are rebuildable by cheaper producers.

## 2. One check, one clause

Failure case: a probe family built its test documents on a base document
that was itself invalid (three required members missing). Every probe
failed for the same undetected reason; every implementation "passed" by
refusing everything; the family measured nothing and reported normally.

Rule: each check exercises exactly one deliberate deviation from a
known-good base, and names the specification clause it exercises. A
failing check must identify the violated sentence. Checks that cannot are
checks whose coverage can rot without detection — and under agent
iteration, will.

## 3. Enforce obligations where the producer can act on them

Failure case: a 21-layer reconstruction. The producer wrote one defective
function at layer 18, passed that layer's checks, built three more layers,
and was refused four hours later by a repository-level check at assembly.
The producer received no signal at the point of error. Fix: a fixture at
the layer that owns the function; the assembly check retained as backstop.

Rule: an obligation enforced only at pipeline end is sound but cannot
steer. Producers converge or exhaust attempt budgets based on where the
signal is. Place the check where the decision is made; keep the global
check as the second net, never the only one.

## 4. No battery without a live positive control

Mutation coverage: deliberately broken implementation variants, each
expected to be killed by the criteria. Required in addition: at least one
variant expected to **survive** — a change the specification licenses
(example here: rewording a refusal message; the spec requires a reason,
not specific text). Interpretation:

- Control survives, mutants killed: criteria discriminate.
- Control killed: the harness condemns everything; kills are meaningless.
- No control, all mutants killed: indistinguishable from a broken harness.

The coverage battery here refuses to emit a report if the baseline fails
or the control dies.

Same rule for any agent evaluation: include cases with known outcomes on
both sides (must-catch, must-pass), or a strict gate cannot be
distinguished from a dead one.

## Provenance

Each rule above was found by running independent producers against the
criteria and inspecting disagreements, not by review of the criteria
text. Criteria quality is an empirical property. Measuring it continuously
is [track 3](track-specification.md).
