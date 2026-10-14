# Promotion

A queue entry is **undeclared**. The primary claim's verdict is three-valued —
a declared condition a run did not measure is `incomplete`, and `incomplete`
never accepts — and an undeclared pressure is weaker than that: it is not a
condition at all. Promotion is the transition from undeclared to declared,
and that transition is exactly a root move on the primary claim.

So there is no promotion mechanism here, and that is deliberate. A promotion
is an ordinary root move: a criterion is written, its path is added to the
recipe's inputs, the gate earns a new output, the root is re-sealed. The queue
feeds the door that already exists. The signature is the key that already
exists.

**No agent signs.** The signature is the one thing outside the proposer's
reach, which is what makes it the anchor the whole bar hangs from. Automating
it would convert a result into a tautology.

## The two bars

A `contraction` is promotable on its merits: every current-root member already
satisfies it, so declaring it evicts nobody and refuses future implementations
that would do otherwise.

An `eviction` is a decision about what the software is. It needs the louder
signature, and the record must name the members it evicts. An eviction whose
casualties are unnamed hides the cost of the decision.

A `repair` is a mandate on the whole population before anything can be pinned.

## The ledger

`promoted/ledger.jsonl` is append-only and holds one record per promotion:
the entry, the pressure it came from, the lane, the pin that was added, the
root before, the root after, the signature, and when. For an eviction it also
names who was evicted.

Today this chain is implicit. The criteria have moved roughly a hundred times
over the project's history, and each move's reason lives in a commit message
or a comment in the recipe — readable by a person, not by a program. The
ledger makes the ratchet a first-class artifact: for any criterion you can ask
which witness forced it, and for any witness you can ask whether it was ever
declared.

A record is refused unless it describes a signed root move. In particular a
record whose `root_before` equals its `root_after` did not promote anything,
and a record with no signature does not describe what happened. The recorded
promotions must also form one unbroken sequence of roots — a gap means a root
move occurred that the ledger does not account for, which is worse than having
no ledger, because it reads as evidence.

## Signature fatigue

The expected failure mode is not a runaway agent. It is a queue that grows
faster than anyone can read, until the signature becomes a formality and the
anchor dies by rubber-stamping. The defences are that ranking is computed
rather than left to the reader, that an entry arrives already re-earned so
reading it is reading evidence rather than a suggestion, and that unranked
pressure accumulating as undeclared is harmless by construction.
