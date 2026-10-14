# Zeta

Reticuli's binary companion. Two bodies, bound, separate orbits, neither
inside the other.

Reticuli names an equivalence class by criteria and holds still: its root is
the acceptance boundary, and moving it is a signed act. Zeta is the other half
of the loop — it puts pressure on the class, reads what the criteria failed to
say, and queues each finding as a verified witness for a signature. Because
nothing here is a pinned input of the primary claim, zeta can run as fast and
as speculatively as the machinery allows. The cost of a bad pressure is wasted
compute, never a corrupted identity.

```bash
python3 zeta/cli.py population jq                        # build a registry
python3 zeta/cli.py sweep jq_surface --population jq     # run a source
python3 zeta/cli.py sweep record_surface --population deployment --mutants
python3 zeta/cli.py queue --population jq                # worst lane first
python3 zeta/cli.py show <entry> --population jq          # one entry in full
python3 zeta/cli.py ledger                               # pressure to identity
python3 zeta/gate.py                                     # zeta's own criteria
python3 tests/test_zeta.py                               # the live probe path
```

Three populations, two sources. `reticuli` is the sealed population;
`deployment` is the authored bytes under each interpreter the claim's host
contract admits; `jq` is three independent implementations of a language
specified by somebody else. `record_surface` asks the record specification's
own validation sentence; `jq_surface` asks the jq language. `--mutants` adds
deliberately broken trees as controls so a free click can be ranked by what it
would actually catch.

No subcommand promotes anything. **No agent signs.**

## What the pieces are

`spec/pressure.md` defines a pressure, the behaviour-class partition it
induces, and the three lanes a partition can fall into.
`spec/population.md` defines membership relative to a root.
`spec/promotion.md` defines the undeclared-to-declared transition and the
ledger that records it. The criteria judge the machinery against fixtures; the
library under `lib/` is generated, so the instrument is itself an equivalence
class.

The three directories a sweep writes — `queue/`, `population/`, `promoted/` —
are outputs, not inputs to zeta's root. A sweep never moves zeta's identity.

## Lanes

| partition over current-root members | lane | what a signature would mean |
|---|---|---|
| all in one class | `contraction` | tightens the class, evicts nobody: a free click |
| two or more classes | `eviction` | chooses an answer and evicts the members holding the others |
| an oracle refuses every member | `repair` | a defect in the whole population, repair before pinning |

`agreement` is easy to mistake for a null result and is in fact the valuable
case: uniform behaviour that no criterion mentions is unpinned surface, and
closing it costs no member. A `split` is not a tightening — it changes what
the software *is*, so it takes the louder signature and must name its
casualties.

## The first sweep, and why its findings are now stale

`record_surface` turns the validation sentence in `spec/record.md` into one
attributable probe family: a well-formed record perturbed one clause at a
time, put to the three document-consuming kernel functions. Against the four
members of root `900b6594` — three reconstructions and the authored
implementation — 78 probes collapsed onto **6 phenomena**, four contractions
and two evictions.

That root has since moved. Promoting the independence guard into
`criteria/boundary_check.py` re-sealed the primary claim at `0c489183`, which
**retired every reconstruction in one step**: all five qualifying trials
earned roots that no longer exist, so the only current-root member is the
authored implementation. The queue's six entries are marked `STALE` — true
records of what was seen at `900b6594`, and no longer arguments about the
class — and a sweep now reports 78 `singleton` dispositions and mints
nothing, because agreement across a population of one is a fact about that
implementation rather than about the class.

This is the coupling working, not a malfunction: a root move costs the
companion its population until the trials are re-earned. It is also the
clearest demonstration of why membership is keyed to a root. A registry that
listed trials that had ever qualified would have reported four members here
and happily minted free clicks on evidence from a class that no longer
existed.

The two evictions are one fact about the surface: `record_canonical` and
`record_digest` accept a document that is not a JSON object in `shipped` and
`r24-claude`, and refuse it in `g2-codex` and `r23-codex`. `record_digest`
over a non-record returns a well-formed 64-hex value in two of four members.

Nobody is defective. `spec/record.md` assigns refusal to "a reader" and names
`record_read` as the reader; it is silent on whether the canonicalizer
validates. All four implementations earned the same root with different
answers, which is what unpinned surface looks like. Resolving it is a spec
decision and therefore a root move, so it sits in the queue at lane
`eviction`, undeclared.

The controls — two trials that failed to qualify and two that qualified
against roots that have since moved — were observed on every pressure and
discriminated nothing. Those trials failed for reasons elsewhere, so every
rank in this sweep is 0. That is a true negative result about the ranker on
this surface, not a missing measurement.

## The second round: two more populations, and a working ranker

The sealed population being down to one member forced the other two, and both
turned out to work without it.

**Deployment pressure needs only one implementation,** because it varies the
host instead. 78 probes against the authored tree under python 3.11, 3.13 and
3.14 collapsed onto 6 phenomena, **all agreement** — identical behaviour
across the whole declared host range. A clean negative result, and the one
population a root move cannot empty.

**The ranker now ranks.** The first sweep's controls discriminated nothing, so
every free click looked equally worth signing. Four mutants of the authored
tree — a canonicalizer that validates nothing, a reader that accepts a
document from the future, one that admits unnamed members, a validator whose
refusal does not refuse — separate the six deployment phenomena into **3
ranked and 3 not**. The three that rank are the future-version clauses; the
well-formed probes catch nothing, which is right, because a correct document
passes a broken implementation too.

**The foreign population found six divergences.** 27 probes against jq 1.8.1,
gojq 0.12.19 and jaq 3.1.1 gave 8 phenomena, 6 of them splits:

| what was asked | split |
|---|---|
| `keys_unsorted` | gojq has no such builtin; jq and jaq return insertion order |
| object key order | gojq normalises to sorted; jq and jaq preserve insertion order |
| `1/0` | jq and gojq error; **jaq returns `Infinity`**, which is not JSON |
| `1e1000` | jq prints `1E+1000`; gojq and jaq print `1e1000` |
| an unpaired surrogate | jq and jaq refuse to parse; gojq substitutes U+FFFD |
| `[55296] \| implode` | jaq differs from both others |

No implementation is consistently the outlier — every split pairs them
differently. This is the population that matters most for the contamination
question: criteria and candidates here share no author lineage.

## The third round: the ranker was ranking redundant work

All three ranked findings from round two were the future-version clause, and
the criteria already test exactly that. The agreement was real; the finding
was worthless. `agreement` asks whether the members behave alike and never
asks whether a criterion already decides it, so the queue was about to spend a
signature pinning what was already pinned.

`zeta/cli.py coverage` answers the second question by running the primary
criteria against each mutant — about 45 seconds a mutant, so the result is
written to `coverage/` rather than recomputed. A killed mutant marks behaviour
already pinned; a survivor marks behaviour the root currently admits an
implementation for, which is a criterion gap with a witness already built.

Eleven operators, baseline earning the gate, **no contradictions**. The
positive control (`reword-refusal`, which must live because the specification
requires a reason and not a sentence) survived, so the harness can detect
survival and the criteria are not pinning the author's prose. Every operator
expected to die did. `discovery-into-totals` and `leak-environment` died too,
which is good news: the discovery bucketing and the environment scrubbing are
both pinned.

**Two survivors are real criterion gaps**, both in measurement honesty, both
contractions that evict nobody:

- `cost-accepts-boolean` — `spec/record.md` says cost keys are "each a
  non-negative number and never a boolean", and removing that guard passes the
  entire gate.
- `tolerance-exclusive` — the cost band is specified and documented as the
  closed interval `[1/tol, tol]`, and making it open passes the entire gate.

A third gap came from reading `gate.py` rather than from zeta: it enumerates
its suites with `glob.glob("criteria/*.py")`, so its read set includes a
directory listing that no pinned path determines. Dropping a failing file into
`criteria/` turns a conforming tree non-conforming, verified by doing it. 24
criteria are pinned and 24 are present, so nothing is adrift today, and a cold
`ret audit` materialises only declared files — so the canonical path is sound
and every recorded root was earned that way. It bites the warm development
run.

All three are staged in
`research/proposals/2026-10-14-three-unpinned-obligations.md` with a drafted
criterion. None is landed: closing them moves the root, which is the
keyholder's to sign.

## What this is not

It is not evidence that the class is tight, that the criteria are complete, or
that the queue is prioritised well. One source has run, against one surface,
on one population, on the authors' machine. The ranker has not yet been shown
to rank anything. Every entry is undeclared and the promotion ledger is empty.

Three of the four stages behind the queue were already built and are not yet
wired in: the differential generator and reducer from
`research/harness/contraction/`, the budgeted probe campaign from
`research/harness/improvement/`, consumer substitution from
`research/harness/substitution/`, and member-against-member judging from
`research/harness/crossjudge/`. The dated records of those experiments stay
where they are; what moves here is generalised machinery.

## One invariant, now enforced

Nothing in zeta may be reachable from inside a producer's room. A pending
pressure that reached a rebuilding producer would be guidance rather than a
criterion, and guidance cannot decide whether a rebuild is accepted.

`criteria/boundary_check.py` in the primary claim makes that permanent, signed
by the keyholder on 2026-10-14. It refuses two shortcuts: a path under `zeta/`
among the pinned inputs, which would put undeclared pressure inside the root
and materialise the queue into a producer's room, and a gate command that
reaches into `zeta/`, which would make the verdict depend on whatever the last
sweep found without pinning a byte. The companion is optional — the primary
claim passes with `zeta/` absent — but the independence is not.

That promotion is **not** in `promoted/ledger.jsonl`, and should not be. The
ledger records promotions of queue entries, and this guard came from reasoning
about the boundary rather than from a pressure that split a population. A
ledger padded with root moves that no witness forced would misrepresent
exactly the chain it exists to document.
