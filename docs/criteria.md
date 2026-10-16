# Writing criteria that carry software

Reproducibility by agents is exactly as good as the acceptance criteria
are sufficient. "Sufficient" has a precise meaning here: a producer that
has never seen the implementation, given only the criteria and the
specification, lands in the same equivalence class. This page is the craft
of getting there — four lessons, each learned from a measured failure in
this repository's own reconstruction trials, stated so they transfer to
any project where agents write the code and tests are the contract.

## 1. Know where your hard criterion is, because it sets the price

Criteria are not uniformly hard to rebuild from. In our trials, producers
of widely varying capability sailed through most layers in seconds each —
and then met one criterion demanding exact byte-level serialization
re-derived from prose, where the field split sharply: some models cleared
it on the first attempt for a fraction of a cent, others burned millions
of tokens across repeated attempts and never passed, and neither price nor
vendor predicted which. Capability against your hardest criterion is a
staircase, not a line.

The transferable practice: identify the discriminating criterion
empirically (run a cheap producer to failure — where it halts is, by
construction, the first obligation that separates producers), then probe
any new model against *that* before funding a full run. The probe costs
cents and predicts the run.

A corollary worth knowing when you write the criteria themselves:
tolerance-banded numerical checks are easier to rebuild from than
byte-exact ones. Demand exactness where identity genuinely needs it — a
digest, an interchange format — and bands elsewhere, or your capability
floor rises for no benefit.

## 2. Every check must be attributable to one clause

The first version of one probe family here built all its test documents on
a base that was itself invalid — it omitted three required members. Every
probe therefore failed, every implementation "passed" by refusing
everything, and the family silently stopped testing what it claimed to
test. Nothing errored; the instrument simply measured nothing, politely.

The rule: each check exercises exactly one deliberate deviation from a
known-good base, and names the specification clause it exercises. When a
check fails, the failure must point at a sentence someone wrote. A
criterion that cannot say *which promise* was broken is a criterion whose
coverage can rot invisibly — and under agent-driven development it will,
because agents iterate against your checks far faster than you re-read
them.

## 3. Place obligations where they can steer, with a backstop where they can't be evaded

One reconstruction trial here grew a twenty-one-layer implementation over
four hours. The producer wrote one defective function at layer eighteen,
passed that layer's local checks, grew three more layers — and learned of
the defect only at final assembly, from a repository-wide check, with the
cause now two removes from the code that caused it. The producer was never
told, at the moment it could have acted, what it got wrong. The fix was
not a new obligation but a moved one: a small fixture at the layer that
owns the function, with the assembly-level check retained as the backstop.

The rule generalizes past layered builds: an obligation enforced only at
the end of a pipeline is sound and nearly useless as feedback. For agent
workflows this is the difference between a producer that converges and one
that burns its attempt budget — put the signal where the decision is made,
and keep the global check as the net beneath it, never the only net.

## 4. A battery without a live positive control proves nothing

To know whether criteria actually constrain an implementation, this
repository runs mutation coverage: deliberately broken variants of the
implementation, each expected to be caught. The non-obvious part is the
variant that is expected to *survive* — a mutation the criteria genuinely
should not care about (here: rewording an error message, since the spec
requires a reason, not a sentence). If that control ever gets caught, the
harness is condemning everything and its kills mean nothing; if every
mutant dies and there is no control, "all caught" is indistinguishable
from a broken harness.

The same applies to any agent-facing evaluation: salt it with cases whose
correct outcome you know on both sides — must-catch and must-pass — or you
cannot distinguish a strict gate from a dead one.

## The meta-lesson

Each of these was found the same way: not by reasoning about the criteria
but by *running strangers against them* and reading where the strangers
and the criteria disagreed. Criteria-writing improves empirically, like
the software it governs. That is the subject of the
[third track](track-specification.md).
