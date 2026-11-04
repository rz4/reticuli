# The tool rebuilding itself

*What was attempted, what held, and what is still open. The ledgers beneath
this document are [`research/metrics/closure-ledger.md`](../research/metrics/closure-ledger.md)
(the count, trial by trial) and
[`research/metrics/genome-map.md`](../research/metrics/genome-map.md) (every
boundary repair and what it closed).*

The three-machine test taken to its limit is the tool regrowing itself from
its own frozen boundary: hand a producer the recipe, the specification, the
acceptance suites and the conformance vectors, with no implementation in the
room, and see whether what comes back is a member of the same class.

## What happened at root `900b6594`

It happened three times, each sealed as a claim whose verdict re-earns
mechanically rather than living in a log.

| trial | sealed claim | what it is |
|---|---|---|
| 1 | `trial-r23-codex` | a tree authored blind by one model family |
| 2 | `trial-r24-claude` | the same, by the other family |
| 3 | `trial-g2-codex` | the grandchild: every layer authored blind by one family while every kernel act — sealing, jailing, rebuilding, computing roots — was performed by trial 2's regrown code, with no shipped code in the loop |

Each tree re-earned `REPO_OK` with all 37 generated modules substituted for
the originals, passed the held-out battery, drove a generation-2 rebuild
through its own kernel, and crosschecked through its own CLI. The third
trial's recursive step means the grandchild then midwifed a
great-grandchild that landed the same root.

The held-out battery sits deliberately outside the root, so it measures
drift rather than identity.

## How different the implementations actually were

Measured text similarity between independent realizations is about 0.12, and
32 of 37 modules have a distinct shape in every realization. The identity
survived three complete replacements of the implementation.

Textual dissimilarity establishes that the reconstructions are not copies. It
does not establish algorithmic diversity, which would need behavioral
clustering, control-flow distance, or mutation-kill profile overlap. None of
those have been applied.

## What it cost, and where the defects were

Getting there took two dozen blind runs and twenty signed boundary repairs,
each one selected by a measured refusal and recorded with its witness.

The pattern in those repairs is the most portable result here. **Every seam
found this way was the unexercised half of a symmetric contract, and every
one sat where code meets the operating system** — filesystem layout, sandbox
policy, store nesting, glob semantics. The pure-logic interior regrew
correctly every time.

## Two things are open, and the first is easy to misread

### The count is 0 of 3 at the current root

The bar counts trials at the *current* boundary, and the boundary kept
learning. A series of adopted changes have intervened since `900b6594`, and
by the bar's own condition 7 each one resets the count to zero.

The three trials above remain sealed and verify today, so `900b6594` really
did carry three. The current root has carried none, and no succession trial
has been run against it at all.

The runs since divide four ways:

| run | root | outcome |
|---|---|---|
| r25 (codex) | `f9b292af` | **qualifying** — full gate, recursive step through its own CLI. Its own counterexample became the boundary move it then qualified against |
| r26 (claude) | `f9b292af` | refused — regrown `audit_deep` reported 311 layers for 18 and omitted the top claim's own gates, so a composed verdict could return `ok` without consulting them |
| r33 (sol56-amazon) | `3302eb8a` | refused in 1.2 minutes on a half-open band where the obligation requires a closed one — a clause signed out of one family's near-miss stopping a different family's actual miss |
| r27 (gemma-4), r28 (gemini) | `3302eb8a` | halted at the capability floor, not refusals. Both located the floor at the identity layer; price does not order it, family does |

r26's counterexample was then adopted, which moved the root again and reset
the count to zero. That is the ratchet charging its intended cost: a refusal
that teaches the boundary cannot also be banked. The reticuli→reticuli arm
is therefore **open, not closed**.

### No trial has ever been re-earned outside this environment

At least one must be re-earned on a machine and by an operator outside it.
CI already re-runs the gate on platform and Python combinations we do not
administer, but CI runs *our* workflow.

The protocol for a stranger is five steps and about thirty minutes
([`research/harness/closure/outside.md`](../research/harness/closure/outside.md)).
It ends in a signed receipt as a pull request, and
`research/harness/closure/receipts/` is still empty. Until one lands, the
self-hosting result is a laboratory result.

## A note on how this record is kept

The closure ledger's own post-mortem is worth reading before trusting
anything above. For nineteen days the README and the ledger's headline read
as a closed 3-of-3 while the live provenance records read 1 of 3 and then 0
of 3 at newer roots. That was recorded late and labelled rather than quietly
corrected, on the standing rule that a ledger which stops at its own best
number is the one failure this project cannot afford.
