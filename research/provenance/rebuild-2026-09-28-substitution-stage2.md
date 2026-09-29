# Substitution stage 2: blind cross-family rebuilds break the consumer in unison

*2026-09-28. The producer-backed half of the substitution demonstrator
([`research/design/substitution-demonstrator.md`](../design/substitution-demonstrator.md));
stage 1 (hand-written dependencies) is
[`research/harness/substitution/`](../harness/substitution/). Runner, claims,
ingested reconstructions, and raw results:
[`research/harness/substitution/stage2/`](../harness/substitution/stage2/).
Run after the room-matches-the-name transition (`16297fb0…`), so the blind
rooms carried no guidance by kernel guarantee and every accepted rebuild
re-earned its source root by kernel refusal.*

## Setup

Three research claims, sealed and audited:

- **`D` — `kvparse`** (root `0459778c…`): a key = value config parser whose
  boundary `C_0` pins only word-valued, distinct-key assignments and the
  empty document. Numeric coercion and duplicate-key meaning are left open,
  deliberately.
- **`P` — `portdoubler`** (root `4191e4d9…`): a consumer that parses
  `port = 21\nport = 80` and doubles the port, expecting 160. Its recipe
  makes `parser.py` a *generated* file, so P's root commits to the contract
  and never to any parser's bytes; a candidate parser is judged by
  `audit(P, produce_from={"parser.py": candidate})` — gates compose.
- **`D1`** (root `76b028ab…`): `C_0` plus the two obligations the consumer
  relies on (numeric values coerce to int; duplicate keys are last-wins).

Six blind reconstructions of `D` from `C_0` alone — no reference
implementation, no guidance — across two producer families, both un-metered:
codex (gpt-6-luna, gpt-6-sol, gpt-6-astra) and headless Claude Code
(sonnet, opus, haiku).

## Round 1 — rebuilds from `C_0`

All six converged, each re-earning `D`'s root; all six are distinct bytes
(6/6 distinct build digests). `P`'s root never moved while its dependency
was swapped beneath it. The matrix:

| reconstruction | D root | C_0 | consumer P | C_1 |
|---|---|---|---|---|
| codex gpt-6-luna | held | yes | **BREAKS** | no |
| codex gpt-6-sol | held | yes | **BREAKS** | no |
| codex gpt-6-astra | held | yes | **BREAKS** | no |
| claude sonnet | held | yes | **BREAKS** | no |
| claude opus | held | yes | **BREAKS** | no |
| claude haiku | held | yes | **BREAKS** | no |

**6/6 pass the dependency's own gate; 0/6 keep the consumer working.**

The failure is one shared reading, not six random ones. Every
reconstruction — both families, all six models — chose last-wins for
duplicate keys (matching the consumer's need) and kept values as strings
(breaking it): the consumer's `cfg["port"] * 2` became `"80" * 2 = "8080"`,
string repetition. The boundary said nothing about coercion, and the
families' shared prior filled the silence the same way, on the wrong side
of the consumer.

Two prior findings meet here. Stage 1 showed a gate-passing dependency is
not thereby substitutable; this shows the divergence *arises on its own*
under real blind rebuilds — no adversarial construction needed. And the
quirkcalc shared-miss result — agreement between producers is not
correctness — recurs one level up: cross-family unanimity among
gate-passers is not consumer-safety. Six independent implementations that
agree with each other all break the consumer identically, so no amount of
crosschecking reconstructions against each other would have surfaced it.
Only the consumer could, and did.

## Round 2 — rebuilds from the tightened `C_1`

The ratchet's move: the consumer break names the missing obligations,
`C_1` pins them (a moved root — a stronger claim), and the same blind
cross-family plan reruns against the tightened boundary.

Same six producers, same blindness, boundary `76b028ab…`:

| reconstruction | C_1 | consumer P |
|---|---|---|
| codex gpt-6-luna | yes | ok |
| codex gpt-6-sol | yes | ok |
| codex gpt-6-astra | yes | ok |
| claude sonnet | yes | ok |
| claude opus | yes | ok |
| claude haiku | yes | ok |

**6/6 reconstructions from `C_1` keep the consumer working** — against 0/6
from `C_0`. The two pinned lines in the check are the entire difference.
One convergence cost a retry: gpt-6-luna's first `C_1` session ended
without passing the gate (a failed attempt, ledgered as such); its second
converged. Every accepted rebuild re-earned `D1`'s root.

## What this establishes, and the honest limit

Established, end to end and with producers: swapping a gate-passing
dependency preserves both claim identities while the realization evidence
changes (point 1 and 2 of the demonstrator's list); consumer-relative
sufficiency is measurably distinct from gate-passing (point 3); a
locally-accepted candidate that violates a consumer assumption exposes the
missing obligation, and pinning it restores substitutability (point 4).

The limit is the standing one: sufficiency is shown against the consumer
contract actually run, not universally. The value is the method — the
consumer finds the missing obligation before it ships, and the ratchet has
a place to put it.
