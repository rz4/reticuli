# Zeta's first sweep, and the root move that retired its population

2026-10-14. Local, standard-library execution; no producer calls. Primary root
before: `900b6594d4ade4d51f1331054437fa311f5f7a73153a722781d4fb701192cc0f`.
Primary root after: `0c489183223aa0940c424d4ec815cb2e12766e271630ab8cd7a2fcb2999044bd`,
signed by the keyholder. Companion claim `zeta` at
`c27c89992956ebe5addb06d0ed1c85ebf24bec4d743646c8c047c070153c9dd6`.

## What was run

```bash
python3 zeta/cli.py population
python3 zeta/cli.py sweep record_surface
python3 zeta/gate.py && python3 tests/test_zeta.py
```

The population was read from the closure harness. Seven succession trials sit
against three distinct roots, so at `900b6594` the population was four
current-root members — `g2-codex`, `r23-codex`, `r24-claude` and the authored
`shipped` — with `r19-codex` and `r21-codex` retired and `r20-codex` and
`r22-claude` refused for carrying no `TRIAL_OK`.

`record_surface` perturbs one well-formed record at a time along each clause of
the Validation section of `spec/record.md`, against `record_validate`,
`record_canonical` and `record_digest`.

## Observed result

78 probes collapsed onto 6 phenomena: four contractions and two evictions.

The two evictions are one fact. `record_canonical` and `record_digest` accept
a document that is not a JSON object in `shipped` and `r24-claude`, and refuse
it in `g2-codex` and `r23-codex`. `record_digest` over a non-record therefore
returns a well-formed 64-character value in two of the four members.

**No member is defective.** `spec/record.md` assigns refusal to "a reader" and
names `record_read` as the reader; it is silent on whether the canonicalizer
validates its argument. Four implementations earned one root with different
answers, which is what unpinned surface looks like. Resolving it is a
specification decision, so both entries sit at lane `eviction`, undeclared.

The controls discriminated nothing on this surface, so every rank is 0. Those
two trials failed for reasons elsewhere. This is a true negative about the
ranker, not a missing measurement.

## The root move, and what it cost

`criteria/boundary_check.py` was added to the primary claim and its path to
the recipe's inputs, refusing two ways for undeclared pressure to reach a
verdict: a pinned path under `zeta/`, and a gate command that reaches into
`zeta/`. Both refusals were tested against deliberately violating copies of
the recipe before the criterion was trusted. The full gate passed, the claim
was re-sealed, and the new root was re-earned cold under the sandbox.

The move retired every reconstruction at once. All five qualifying trials had
earned roots that no longer exist, so the current-root population fell to one
member: the authored implementation. Two consequences followed immediately and
are worth recording because neither was anticipated when the module was
designed that morning.

First, the six queue entries became **stale**. A split is relative to a root,
and these partitioned members of a class that no longer exists. They remain
true records of what was seen at `900b6594` and are no longer arguments about
the current class. Zeta now marks them rather than deleting them, sorts them
last, and says so when the queue is read.

Second, a population of one exposed a hole in the instrument. Agreement across
a single member is a fact about that implementation, not about the class, yet
the classifier would have minted it as a contraction — a free ratchet click on
no evidence. A `singleton` disposition was added and is not queueable; a sweep
against the current population now reports 78 singletons and mints nothing.

## What this establishes

That the two halves are coupled exactly as intended: pressure runs at whatever
speed the machinery allows and cannot move an identity, while a root move
costs the companion its population until the trials are re-earned. That
membership keyed to a root is load-bearing rather than fastidious — a registry
listing trials that had ever qualified would have reported four members after
the move and minted clicks on a dead class.

It establishes nothing about whether the class is tight, whether the criteria
are complete, or whether the queue is ranked well. One source has run, against
one surface, on one population, on the authors' machine, and the ranker has
not yet been shown to rank anything. The promotion ledger is empty: the
boundary guard came from reasoning about the boundary, not from a pressure
that split a population, and recording it as a promotion would misrepresent
the chain the ledger exists to document.

The next step is succession trials against `0c489183` to restore a population
with more than one member.
