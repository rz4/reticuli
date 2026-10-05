# Succession r4 — three pins steer same-day; the deep audit's depth is the new silence

*2026-10-05. The codex lineage regrown across the root move the day
itself produced: layers core–seal at `3e7dc827…`, the rest at
`79bce6fb…` after the authoring-and-sandbox bundle landed mid-run
(paused on the codex quota, resumed when it refreshed). Predictions
were stated before the run and amended at the pause
(predictions_r4.md, P1–P11); this record scores them. Trees in
`lineages-r4/`; the cross-judging matrix and the pair silence maps are
the scoring instruments.*

## The run

All twenty layers regrown blind, every layer gate passed — including
`build` and `authoring` under their bundle-tightened checks, both on
first attempt. Held-out tests: 102 of 103 — the one failure is OURS,
not the tree's (below). The judge's bootstrap: verify/refuse verbs all
correct; the gen-2 core rebuild died on a codex CLI crash (Rust abort,
exit −6) — infrastructure, not semantics; retry pending.

## Predictions, scored

- **P1, verdict vocabulary — HELD.** In the cross-judging matrix the
  r4 tree produces zero verdict-word findings: `failed` for a failed
  gate, `broken` for identity damage. The r3 trees keep their era's
  words beside it — three eras of this one seam now read: free → free
  → pinned-and-converged.
- **P2/P3/P4 (scrub canary, timeout direction, closure) — HELD by
  gate.** The pinned layers re-earned their tightened checks blind;
  closure_check passes on the substituted tree's run (its refusal came
  elsewhere — below).
- **P5, reference — HELD.** The regrown reference agreed with the
  regrown kernel on every conformance vector, first attempt.
- **P6/P7, no halo / freedom stays free — HELD.** Pair maps
  {original, codex-r3} = 467 divergent / 236 consumed vs
  {original, codex-r4} = 485 / 238: flat within fresh-sample variance.
  The bundle's pins steered exactly their named behaviors and bought
  nothing else; unconsumed form still floats.
- **P8, held-out tests — HELD with one asterisk.** 102/103; the
  failure is the bundle's own second authoring draft embedding a
  nested path in a guidance hint, caught by the self-contained scanner
  on CI and in the judge the same hour. The r4 tree is innocent; the
  criterion was fixed (third draft, flat fixture) and the scanner's
  catch is recorded in the bundle revision.
- **P9, the envelope — SUPERSEDED by a sharper refusal.** The
  substituted full gate failed at 22.3 minutes, UNDER the 1800 s
  ceiling — not the predicted timing wall but a genuine criterion
  refusal (below). The timing question stands for a tree that passes.
- **P10, authoring default — HELD.** The r4 tree packs fresh claims at
  format 3 and mints the SAME root as the original (`cd117e55…`) for
  identical content — the convergence the bundle purchased, visible in
  the matrix as two eras with one name each.
- **P11, sandbox signal — HELD.** The r4 tree's rebuild result names
  `seatbelt`, like the original; the r3 trees stay silent beside it.

Three pins signed in the morning, carried by a blind descendant in the
evening. Pin-steering now has a same-day demonstration.

## The discovery: audit_deep's transitive closure is unpinned

The identity judgment refused the r4 tree — `self_check`'s deep-audit
assertion: surface's composed audit judged 1 layer instead of 18. The
regrown `registry.audit_deep` recurses one level (direct components
only); the original walks the whole chain. The r3 tree's audit_deep is
ALSO one-level (never judged — r3 ran no full gate); the r2 tree's
recursed fully and passed. Independent draws fill the depth
differently because `exchange_check` exercises audit_deep on a fixture
chain too shallow to force recursion: a layer-admissible module that
is repo-inadmissible, the gate-closure class of finding one level up.
Staged: `research/proposals/pin-deep-audit-transitivity.md`.

This is the negative-space loop behaving exactly as designed, and
worth saying in its vocabulary: the boundary did not fail — the
whole-repo criterion REFUSED the tree, which is the system working —
but the refusal localized a seam the layer boundary is silent about,
and the witness is a conforming implementation that reports a deep
chain healthy after checking its first link. D_t in one sentence.

## Postscript: the bootstrap's two failures are two more seams

Both bootstrap failures reproduced on retry and both diagnosed to the
same silence — the sandbox contract beyond "gates are jailed":

- **The descendant jails its producers.** Its `_produce` wraps the
  producer in the gate sandbox; codex dies before doing anything (its
  runtime cannot allocate a stack guard page in the jail) and the jail
  denies network besides, which ends every model producer. A
  descendant that judges but cannot procreate — generation 2 is
  unreachable through it. Nothing pins producer freedom. Staged:
  `research/proposals/free-the-producer.md`.
- **The descendant's jail floor is below the contract.** Its
  `(deny default)` profile does not allow `/dev`, so the first gate
  line redirecting to `/dev/null` dies — the repo audit refuses
  REPO_OK in two minutes, a FALSE refusal, reported with no detail.
  The jail passed its layer check because run_check's fixtures never
  touch `/dev`. Staged: `research/proposals/pin-the-jail-floor.md`.

With these, the generation's discovery count is three (deep-audit
transitivity, producer confinement, the jail floor) — all in the same
region the keyholder named in advance: "the remaining nested-gate and
sandbox-signal questions." The sandbox-signal pin (P11) made verdicts
NAME their jail; these two are about what the jail may and must not
contain. The region was flagged, the samples landed in it, and each
landing is now a staged pin.

## Ledger note

One generation: three convergence confirmations (P1/P10/P11), two
no-halo confirmations (P6/P7), one infrastructure flake (codex crash),
one self-inflicted criterion defect caught by two instruments within
the hour (the scanner on CI and in the judge), and one new seam with a
staged pin. The r4 tree does the parent's job in the matrix (judges,
refuses, reproduces, names its jail) and is refused by the parent's
identity for a reason that is itself the next click. The loop's
output, as ever, is not the tree — it is the boundary's next edit.
