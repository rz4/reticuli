# Contraction instrument (base64 pilot)

*Research tooling — not normative, not pinned, outside the repository root.*

The measuring tools for the reconstruction-basin contraction experiment
([`research/design/authority-and-basin-contraction.md`](../../design/authority-and-basin-contraction.md),
pilot in [`research/design/pilot-base64-preregistration.md`](../../design/pilot-base64-preregistration.md)).
Given a set of implementations of one claim, it measures how much behavioral and
structural freedom the boundary still leaves, finds where the implementations
disagree, and reduces each disagreement to the minimal input that exposes it.

Everything here runs with no producer and no network. `pilot.py` self-tests the
whole pipeline over the hand-written fixtures, so the instrument is proven before
any rebuild draws on the codex window.

```
python3 research/harness/contraction/pilot.py [outdir]
```

## The pieces

| file | what it does |
|---|---|
| `boundary.py` | the boundary `C`: the gate (round-trip + RFC 4648 §10 vectors + pinned decode rules) and `observe`, the canonical outcome. `C_0` pins only the happy path; `tighten` adds accepted counterexamples |
| `probes.py` | the frozen probe set `X`: hand seed corpus over the strictness surface + seeded fuzzer (seeds 0..999) + round-trip inputs. No model in this loop |
| `differential.py` | run every survivor over `X`, build the disagreement matrix, list the inputs they do not all agree on |
| `reduce.py` | shrink a disagreement to its shortest **partition-preserving** witness, and the partition that identifies its class |
| `structure.py` | `d_struct`: name-blind token-edit distance between sources, plus clustering — the structural-diversity metric that keeps the thesis honest |
| `metrics.py` | one generation's numbers from the frozen definitions: `R`, `S`, `D`, `U`, `A`, `Y`, `Y*`, `K*` |
| `pilot.py` | orchestrates one generation and self-tests on the fixtures |
| `fixtures/` | six hand-written base64 codecs, structurally and behaviorally varied, all passing `C_0` — the instrument's test input |

## Three refinements the shake-down forced (before freezing)

The self-test changed three metric *definitions* from the first-draft
pre-registration. Each is now reflected in the pilot pre-registration and must
be part of what the keyholder freezes:

1. **A disagreement is a partition, not a string.** Deduping novel witnesses by
   exact minimal-witness string counted `!`, `*`, `+` as three separate
   questions — 433 of them. The identity of a disagreement is the
   *who-agrees-with-whom partition* over the survivors; near-duplicate inputs
   collapse to one question, one adjudication. (433 → 7.)
2. **The reducer must preserve the partition.** Minimizing for "still splits
   somehow" let a URL-safe question collapse into a generic junk-character one
   on the way down. The reducer now shrinks only while the same partition holds.
3. **Rejection is rejection.** Counting a different exception *type*
   (`ValueError` vs `binascii.Error`) as a behavioral difference made two strict
   decoders look maximally divergent. The canonical outcome collapses every
   exception to one "rejected" token.

The instrument also correctly raised the structural-collapse alarm (falsifier
F3, `S → 0`) when a careless adjudication accepted a counterexample that killed
five of six implementations — which is why the simulated keyholder guards the
structural floor.
