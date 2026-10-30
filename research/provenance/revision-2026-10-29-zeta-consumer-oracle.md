# Zeta learns the consumer oracle: the repair lane gets its first real source

2026-10-29. **Zeta's** root moves `a7a0e3fa…` → `b0e235d249c7b0e8...` (the
companion claim's own identity, not the primary's — the primary claim holds
at `f2d49443…`, unaffected, because `boundary_check` keeps zeta out of its
preimage). An internal click on zeta by the same bar `docs/transitions.md`
sets: the pinned edits are `zeta/criteria/split_check.py`,
`zeta/spec/pressure.md`, `zeta/spec/population.md`, and one new produce step
in `zeta/reticuli.toml`.

*(The root passed through `e4bd7cc0` on the first draft; an adversarial review
of that draft found seventeen defects — several of them the exact
harness-bug-as-finding trap this instrument exists to refuse — and the fixes
moved the pinned criterion and spec again to `b0e235d2`. The review and what
it changed are the last section of this record, because they are the most
useful part of it.)*

This is the first step of the replacement-grade program's zeta arm: the
consumer-substitution finding, moved from a hand-rolled harness
(`research/harness/substitution/`) into a zeta source that re-earns like any
other finding.

## Why it belongs in zeta, not reticuli

The end goal is an agent driving zeta to a replacement-grade rebuild of an
arbitrary repository. Reticuli stays tight — it names the boundary and decides
membership, fourteen verbs, no growth. Zeta measures width. "Does a rebuild
keep a consumer working" is a width question — divergence on surface the
dependency's own criteria do not pin — so it is zeta's to answer, and it
needed nothing new from reticuli: the observation is `kernel.audit(consumer,
produce_from={output: realization_bytes})`, the exact composition the kernel
already uses for mutation. No new verb; the fourteen stay fourteen.

## The mechanism: a consumer is an oracle, and the oracle decides the lane

The pressure spec already reserved the **repair** lane for "an outside
standard that can say every member is wrong," and nothing produced it —
differential pressure has no oracle, so unanimity was always agreement. A
consumer is that oracle. Each realization of a dependency, substituted under
the consumer, either keeps the consumer's gate or breaks it, and that verdict
rides in the observation as `satisfies_oracle`. When any observation carries
it, `classify` decides the lane from the verdict rather than the behaviour
partition:

- every realization keeps the consumer → **contraction** (the obligation
  holds across the class; pinning it evicts nobody);
- the realizations split → **eviction** (the consumer's obligation is the
  deciding criterion; the breakers are evicted when it is pinned) — and this
  is third-kind **contact**, two trees that both earned the dependency's root
  disagreeing about whether they are the software a consumer can live with;
- no realization keeps the consumer → **repair** (the dependency's boundary
  is universally insufficient; a pin cannot simply be added).

The last case is the one that matters, because it is the substitution finding:
unanimity among independent rebuilds that is a *defect*, not a free click. The
bit is what tells them apart — the same three members returning the same bytes
are an ordinary contraction without it and a repair with it — and because it
travels in the retained observations, the finding re-earns through its entry's
own portable gate exactly as a differential one does. That re-earning is the
whole point of zeta's entries: a human reading the queue reads a replayable
claim, not a report.

## The acceptance test: the substitution finding, reproduced as one sweep

The 2026-09-28 stage-2 run — six blind cross-family rebuilds of a `kvparse`
dependency, 6/6 passing the dependency's own gate, 0/6 keeping the consumer —
was a bespoke harness (`run_stage2.py`, ~160 lines). It now reproduces as:

```
zeta/cli.py population consumer \
    --dependency research/harness/substitution/stage2/claims/D \
    --consume     research/harness/substitution/stage2/claims/P \
    --realizations research/harness/substitution/stage2/impls \
    --output parser.py
zeta/cli.py sweep consumer_surface --population consumer
    -> dispositions {"repair": 1}, one entry minted
```

The entry sits in the repair lane against the dependency's root `0459778c`,
holds all six realizations in one behaviour class `{"consumer": "breaks"}`
each carrying `satisfies_oracle: false`, and its own gate re-earns the
classification cold. The eviction lane was verified against a mixed
population (one C₀-breaking and one C₁-keeping realization → split →
eviction), and the criterion now pins all three dispositions plus the
distinction that the same values with no oracle bit are an ordinary
contraction.

## What this is and is not

It **is** the only non-circular test of replacement the program has found: a
probe battery is always an aperture (jq measured 17.6% recall against a
preregistered 30%, falsified), while a consumer's gate is ground truth for
the surface that consumer exercises. It **is** the second half of the
declared-freedom mechanism — a surface declared free on a dependency is free
until a consumer depends on it, which is exactly where the substitution result
says the obligation lives.

It is **not** a replacement-grade certificate. It establishes replacement *for
the named consumers*, which is the only meaning the phrase ever honestly had,
and the reconstruct-codebase skill's grade vocabulary already says so:
"replacement-grade over this probe" is honest, "replacement-grade" alone is
not. And it does not reach the fourth rung: it measures the members in hand
against a standard this system wrote, so it is contact at its strongest, never
abduction.

## The review, and the false findings it caught in the first draft

The first draft passed `zeta/gate.py` and `split_check.py` and reproduced the
repair finding. An adversarial review of the diff then found **seventeen
defects the criteria did not catch**, and the important ones were not rough
edges — they were the instrument manufacturing *false findings* that re-earned
cleanly, which is strictly worse than finding nothing. The ones that mattered,
and the fix each got:

- **A wrong cwd minted a false repair with the same digest as the true one.**
  The consumer path was stored repo-relative and resolved against the process
  cwd, so `cd zeta && sweep …` failed to find the consumer, every member came
  back `ClaimError`, and the all-fail reading produced an identical-looking
  repair. Fix: `load()` rehydrates the consumer path (and the realization and
  tool paths) against the repo, like it already did for member paths; the
  verdict is now cwd-independent, verified from `/tmp`.
- **A one-character typo in the output name minted a false *contraction*.**
  `produce_from` with a key that names no produce step substitutes nothing and
  the consumer passes on its own bytes — so every realization "kept" the
  consumer, a free ratchet click on a universally broken class, the worst
  failure direction. Fix: the driver refuses unless the output is a produce
  step of the consumer, and reads an absent verdict as not-measured.
- **A missing host tool, a drifted consumer, or an `environment` gate all
  read as "the realization broke the consumer".** The driver took only
  `audit(...)["ok"]`, collapsing untested into disproven. Fix: it inspects the
  gate statuses and sets a verdict bit only on a clean pass or a genuine
  `failed`; `environment`, `mismatch`, and `claim_ok=False` carry no bit.
- **A README globbed into the realizations directory counted as a member.**
  The builder asserted `earned_root = dependency_root` without checking,
  making `load()`'s membership invariant vacuous. Fix: the builder audits each
  realization against the dependency and routes non-earners to `refused` —
  verified: a non-parser is refused, "does not earn the dependency's own gate".
- **A repair from a single real verdict.** The singleton guard counted
  observations, not verdicts, so five path typos plus one break minted a
  class-wide repair. Fix: an oracle lane requires at least two members that
  genuinely faced the standard, pinned in the criterion.
- **`jq_surface` against the consumer population ran `audit(".")` on the whole
  reticuli claim six times (a 120s hang) and `record_surface` crashed with an
  uncaught `TypeError`.** Any source could be pointed at any population. Fix:
  the substitution driver answers only `audit_consumer` and refuses any other
  call in band; a mismatched pairing now yields clean `invalid` probes with a
  one-line note.
- **The pinned eviction-lane fixture was tautological** — it passed with the
  oracle branch deleted, because its values already differed. Fix: the fixture
  now uses identical values so the split can only come from the verdict,
  confirmed to fail if the branch is removed. And the pinned spec sentence that
  claimed an oracle finding "re-earns exactly as a differential one does" was
  false (the bit *is* the classification, so the gate checks a weaker thing);
  it now states exactly what the gate does and does not establish, and why the
  not-measured safeguard is the load-bearing discipline.

The lesson is the one the whole program keeps relearning: `src/reticuli/` and
zeta's `lib/` are outside their roots by design, so the acceptance boundary had
no opinion about any of this, and only an adversary reading the diff caught it.
The fixes that belong in the boundary — the criterion now pins absent-as-not-
measured, the two-verdict floor, and the verdict-partitioned eviction cost — are
in; the ones that live in generated code (the driver's gate-status reading, the
builder's membership audit) are tested but unpinned, which is the standing
`every-gate-path-meets-the-jail-floor` gap one more time.

## Re-earned

```
zeta/gate.py                   zeta-ok, 8 suites, at zeta root b0e235d2
ret verify zeta                ok, b0e235d2
ret verify .  (primary)        fresh, f2d49443 — unaffected
python3 gate.py (primary)      repo-ok
pytest tests/                  223 passed
consumer sweep                 repair finding reproduced; entry gate re-earns;
                               cwd-independent; README refused; typo→not-measured
```

## Open, and whose it is

- **An external, non-Python target.** The population and probe generalize, but
  every member probed to date is Python-shaped. The universal mode is the
  process boundary (stdin/stdout/exit), already proven by the jq population;
  wiring a consumer population whose members are built artifacts rather than
  importable trees is the next step and is not done here.
- **Zeta's own succession trial.** The instrument that will certify
  replacement has never been regrown blind. It is the weaker sibling — now
  nine lib modules, eight criteria — and pointing it at strangers' code before
  it has re-earned its own boundary is the gap the stack's integrity rests on.
  Staged, not done.
- **Declared freedom** stays prose until the format ruling
  (`research/proposals/2026-10-29-declared-freedom-in-the-recipe.md`), so the
  eviction lane can *find* the contract/latitude split but cannot yet apply
  it automatically.
