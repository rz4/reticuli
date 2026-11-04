# Passing the gate does not make an implementation substitutable

*The harness is [`research/harness/substitution/`](../research/harness/substitution/);
the plan and rationale are in
[`research/design/substitution-demonstrator.md`](../research/design/substitution-demonstrator.md);
the full record of the rebuild run is
[`research/provenance/rebuild-2026-09-28-substitution-stage2.md`](../research/provenance/rebuild-2026-09-28-substitution-stage2.md).*

A root names an equivalence class: every implementation that passes the
criteria is a member, and members are interchangeable *as far as the criteria
go*. The question this experiment asks is whether that is the same thing as
being safe to swap in under a program that depends on you.

It is not, and the gap is measurable.

## The setup

A config parser claim whose tests deliberately leave two things unpinned:
numeric coercion and duplicate keys. A consumer claim that depends on both —
it doubles a duplicated value and does arithmetic on a numeric `port`.

The parser's boundary is honest about what it pins. It is simply silent
about the rest, which is the ordinary condition of almost every test suite.

## Stage 1: three hand-written parsers

All three pass the parser's gate. Only one keeps the consumer working. The
two that pass-but-break expose exactly the obligations the consumer had been
relying on silently.

## Stage 2: six real blind rebuilds

The hand-written parsers were replaced with blind cross-family
reconstructions of a sealed `kvparse` claim — three by OpenAI models, three
by Anthropic models — each judged by auditing a sealed consumer claim with
that reconstruction substituted for its generated parser.

| | result |
|---|---|
| passed the parser's gate | **6 of 6** |
| distinct implementations, by bytes | **6 of 6** |
| kept the consumer working | **0 of 6** |

Every model in both families made the same choice: keep values as strings.
The consumer's `port * 2` became string repetition.

**Agreement between independent rebuilds is not safety.** Two families,
six samples, six distinct implementations, and one identical reading of the
tests' silence — on the wrong side of the consumer. Nothing inside the
parser's own boundary could have detected this. Only the consumer could
expose the missing obligation, and did.

This is the concrete form of a general caution: N-version programming
assumes independently built versions fail independently, Knight and Leveson
showed that is false even for separate human teams, and models additionally
share pretraining corpora.

## The repair is the protocol's own move

Every consumer break names an obligation the boundary forgot. Pin it into the
tests — two lines, in this case — and the name moves, because it is a
different and stronger claim.

Rerunning the same six blind rebuilds against the tightened criteria:
**6 of 6 keep the consumer working.**

A weak boundary is not a dead end. It is where the tightening starts, and the
breaks tell you exactly where. The procedure for making that move is in
[`docs/transitions.md`](../docs/transitions.md).

## What this does and does not establish

It establishes that gate-passing and consumer-safe are different properties,
and that the difference shows up immediately with real producers rather than
being a theoretical concern.

It does not establish how often this happens in practice. One claim pair,
one open surface, two families, six samples. The mechanism is demonstrated;
the base rate is not measured.
