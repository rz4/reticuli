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

## Controls

The retired and refused groups are **not** members and never decide a lane.
They are observed on every pressure, and a control whose behaviour falls
outside every class the members occupy is what ranks a free click: the
pressure would have caught a real non-member.

A population with no current-root members cannot support any argument about
preserving the class, and the registry refuses to load.
