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

## Kinds: how much a finding establishes

The lane says what signing a finding would **cost**. It does not say what the
finding **establishes**, and those are independent axes. A contraction can be
worthless — every member agreeing about something three criteria already pin —
or it can be the strongest thing in the queue, because the specification has
no position on the topic at all. Conflating cost with strength is how five
redundant entries sat at the top of a queue wearing the same label as a real
gap.

Findings come in four kinds, weakest first.

| kind | establishes | assigned when |
|---|---|---|
| **first — sighting** | behaviour is unpinned and nothing came of it | the members agree, and nothing stronger was measured |
| **second — evidence** | a trace: the criteria would let a broken implementation through | the pressure separates a *surviving* mutant |
| **third — contact** | the class contains a contradiction right now | members that both earned the root disagree |
| **fourth — abduction** | the specification has no position on the topic; closing it adds a clause, not a criterion | a source names the foreign silence whose shape it carried across |

Third kind is the urgent rung. A contradiction between things that both earned
the root is not a claim about some future implementation, it is a claim about
the members in hand, and it is why an eviction needs the louder signature.

Fourth kind is the rare one, and it is the only rung a pressure derived from
this system can never reach. Probes read out of the specification, and mutants
made by perturbing the implementation, can at most drive the specification
toward being a fixpoint of itself: if the system has no notion of some thing,
nothing inside it will propose one. Reaching the fourth rung takes a source
that looks somewhere else — a foreign population's silences, a composition
whose interface neither side had to state, an environment axis nobody
declared.

**A rung is assigned from what was measured, never asserted.** The members
decide first. Coverage may raise a sighting to evidence, because a surviving
mutant is a trace, and may never reach contact, because a tree somebody built
to be broken is weaker than two members that both earned the root — and
nothing may demote contact. The fourth rung must be earned by naming the
population and the silence that were carried across: no system can assert
novelty about its own vocabulary, so the claim is only ever as good as its
provenance.

## Redundancy: a free click must still buy something

Ranking says a pressure would catch a broken implementation. It does not say
the criteria would miss it. Those are different questions, and conflating them
is how the first ranked findings were produced: all three were the
future-version clause, every member refuses a document from the future, and
the criteria already test exactly that. The agreement was real and the finding
was worthless, because `agreement` asks whether the members behave alike and
never asks whether a criterion already decides it.

The second question has a mechanical answer, and it reuses the controls. A
mutant is a change to an implementation; the criteria are what decide
membership. So run the criteria against each mutant:

- a **killed** mutant marks behaviour that is already pinned, and a pressure
  separating only killed mutants is redundant with criteria that exist;
- a **surviving** mutant marks behaviour the root currently admits an
  implementation for — a hole in the criteria, with a witness already built —
  and a pressure separating a survivor is a free click that buys something.

This is ordinary mutation analysis pointed sideways: scoring asks whether a
suite is strong enough to keep, while the same measurement here says which
pressure deserves a signature. A redundancy verdict is relative to the
criteria that produced it, so it carries their digest; re-pin a criterion and
the judgement is made again.

Two failure directions, and they are not symmetric. A **false survival** sends
a signature after a gap that is not there, and the expectation column catches
it: every operator declares whether it must die, must live, or is unknown, and
a contradiction is reported rather than averaged away. At least one operator
must be a positive control that has to live — without it, "every mutant
killed" cannot be told apart from a harness that cannot detect survival at
all, which is exactly what the first four operators were. A **false kill** is
worse, because it reads as "already pinned" and quietly empties the queue of
the findings worth having. The room staged for a mutant run is a subset of the
repository, so the unmutated tree runs first and must earn the gate; if it
cannot, every kill measured there would be an artefact of staging and the
report refuses to be one.

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
