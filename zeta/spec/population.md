# Population

A **population** is the set of implementations a pressure is put to. Zeta is
parameterized by it: the machinery knows nothing about reticuli specifically,
and the reticuli members and the jq implementations are two instances of the
same thing.

## Membership is relative to a root

A member is a member **of a root**. A trial that earned its verdict against a
criterion set that has since moved is not evicted retroactively — it earned
what it earned — but it cannot be used to argue that a proposed criterion
preserves the current class, because it never faced the current criteria.

The repository's own history supplies the case. Seven succession trials sit in
the closure harness against three distinct roots:

| state | trials | why |
|---|---|---|
| current | the trials whose `expect_root` is the repository's root, plus the authored implementation | these faced the current criteria and earned them |
| retired | trials that qualified against a root that has since moved | re-earned, never inherited |
| refused | trials with no `TRIAL_OK` | did not qualify |

One of the retired trials is the instructive one: it qualified, a later
comment-only change to a committed acceptance program moved the root, and it
was regrown under the new root as a separate trial. A registry that simply
listed "trials that qualified" would count it as evidence that a proposed
criterion preserves the class. It is not evidence of that.

## The authored implementation is a member

The implementation under `src/` is probed alongside the reconstructions. It is
one answer in the class, not the definition of the class, and a pressure that
splits it from the reconstructions is a finding about the specification rather
than a finding about the reconstructions.

Resolving it must be explicit. An editable install of the authored package
will answer an `import` from inside a reconstruction's probe if the import
path is merely prepended to the environment, and the probe then reports the
authored behaviour under the reconstruction's name. The driver therefore
inserts the member's own tree and refuses an import that resolved anywhere
else.

## Three populations

**reticuli** is the sealed population: reconstructions plus the authored tree,
keyed to the current root. It is the only one that speaks directly about the
class, and the only one a root move empties.

**deployment** varies the host rather than the implementation. The claim
declares `requires = ["python>=3.11"]`, so every interpreter in that range is
a deployment it permits, and the same bytes under each are several things the
claim equally allows. A split here is not a disagreement between
implementations; it is the root failing to determine behaviour across its own
declared host contract. This population survives a root move, because its
member is the authored tree and that always carries the current root.

**jq** is foreign: three independent implementations of a language specified
by somebody else. It is the control for the contamination the reticuli
population cannot escape, where criteria and candidates share an author
lineage. Nobody sealed these, so membership is not relative to a reticuli
root and the registry records what the population is instead of pretending to
an identity. Treat it as a population, never as a claim.

**consumer** is realizations of a dependency, keyed to that dependency's
root, to be put to a consumer that relies on it. The members are independent
blind rebuilds of the dependency — each a file of bytes that passed the
dependency's own gate — and the consumer is not a member but the oracle they
are measured against: a sealed claim whose gate re-earns, or does not, with
each realization substituted in. A root move on the dependency retires the
realizations exactly as it does the sealed reticuli population. This is the
only population whose pressure can produce the repair lane without a foreign
oracle, because the consumer *is* the oracle — and it is the machine form of
the substitution finding, where six rebuilds agreed and all six broke a
consumer that only it could expose.

## Controls

The retired and refused groups are **not** members and never decide a lane.
They are observed on every pressure, and a control whose behaviour falls
outside every class the members occupy is what ranks a free click: the
pressure would have caught a real non-member.

**Mutants** join that set when the sealed population cannot rank anything.
A mutant is the authored tree with one targeted edit, usually to a refusal
path, and it is never a member: nobody sealed it and it would not earn the
root. Its only job is to answer a pressure differently from the members. A
pressure no mutant can be told apart from a conforming member would not have
caught a broken implementation, whatever else it is.

**A control must have answered.** Attempting is required before a control can
discriminate: one that could not run the pressure never faced it, and
counting that as discrimination manufactures rank out of incompatibility.
Python mutants scored four against a population of external programs by
reporting, four times over, that the function did not exist. The rule is now
that only a control returning a value or an in-band refusal can rank a
pressure, and a population driven by external processes is told that its
mutants were skipped rather than left to produce a silent zero.

A population with no current-root members cannot support any argument about
preserving the class, and the registry refuses to load.
