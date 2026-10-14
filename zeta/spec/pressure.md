# Pressure

A **pressure** is an executable question put to every member of a population
at once. It is not a criterion, not an obligation, and not a test the software
has to pass. It is a way of asking what the criteria failed to say.

A pressure carries a `call`, its `args`, the `source` that generated it, and
the `origin` it came from — for a specification-derived family, the sentence it
exercises. Nothing about a pressure is pinned by the primary claim, and
nothing about it can change a verdict.

## What a pressure does to a population

Running a pressure against every current-root member partitions them into
**behaviour classes**. The partition is the finding; the lane follows from it.

| partition | disposition | lane | what declaring it would mean |
|---|---|---|---|
| one class holds every member | `agreement` | `contraction` | the class tightens and nobody is evicted: a free ratchet click |
| two or more classes | `split` | `eviction` | one answer is chosen and the members holding the others are evicted |
| an outside standard refuses every member | `repair` | `repair` | a defect in the whole population, to be repaired before it can be pinned |
| nothing could be observed | `invalid` | — | not a finding about the specification |

`agreement` is the valuable case and it is easy to mistake for a null result.
Every member behaving the same way on an input no criterion mentions is
exactly the unpinned surface worth closing: declaring it costs no member and
refuses every future implementation that would do otherwise.

`split` is not a tightening. Two members cannot both be right about one
input, so declaring either answer changes what the software *is* rather than
narrowing what counts as an instance of it. That is a different decision and
it takes the louder signature.

`repair` requires an oracle — an outside standard that can say every member is
wrong. Differential pressure has no oracle, so it can never produce this
lane: with nothing to compare against, unanimity is agreement.

## The equivalence

Two members are in the same class when they did the same thing. Refusal
**wording is outside that equivalence**, on purpose. `spec/record.md` requires
a reader to refuse "in band and with a reason"; it does not fix the sentence.
A criterion that pinned the sentence would make membership depend on the
author's prose, which is exactly what an equivalence class is not. Divergent
wording is still recorded, because knowing that it diverges is worth having.

An in-band refusal and a crash are **not** the same class. Refusing is
behaviour the specification describes; crashing is not.

## Phenomena, not probes

A sweep asks every clause of every surface, so one behavioural difference gets
witnessed many times over. Those are witnesses of one **phenomenon**, not
separate findings, and counting them separately inflates a queue until nobody
reads it. A phenomenon is identified by the surface probed, the disposition,
and the partition labelled by outcome kind — which separates "every member
accepted" from "every member refused" while still collapsing twenty-four
refusals of twenty-four documents into one entry.

The witness kept is the one whose **rank it can account for**: discriminating
power first, then simplicity. A rank borrowed from a witness the entry does
not retain could not be re-earned from the entry's own bytes. The identifiers
of the collapsed witnesses travel with the entry, so breadth stays visible and
nothing claims to have been checked that was not.

## Ranking

Every `agreement` is free, but free clicks are not equally worth a signature,
and the signature is the scarce resource. **Discrimination is measured, not
judged.** The closure harness already holds the controls: trials that failed
to qualify, and trials that qualified against a root that has since moved. A
pressure that every current member agrees on and that a known non-qualifier
answers differently is a click that would have caught a real non-member.

Controls never decide a lane — they are not members. They only rank the queue.

## Sources

A source is free to be fast, speculative, and wrong, because what it emits is
undeclared until a signature says otherwise. The cost of a bad source is
wasted compute, never a corrupted identity. That asymmetry is what licenses
running sources in parallel, chaotically, at whatever speed the machinery
allows.

Attributability is the one discipline a source owes. A specification-derived
family must perturb a **well-formed** base document one clause at a time; a
base that is itself invalid makes every case refuse for the wrong reason, and
the family silently stops testing what it claims to test.
