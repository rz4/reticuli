# The genome map — the boundary as a heritable information structure

*2026-10-09, at root `71fd7559…`. A standing instrument, regenerated per
boundary version. Nothing here moves a root; this documents what the
root is made of.*

The framing this map serves: what persists across the project is not
any implementation (the phenotype — disposable, measured enormously
variable) and not any single root (a snapshot), but the accumulating
pin set — the genome. Each pin is a gene: selected by a seam (a trial
refusal), fixed by a keyholder signature (the root move), and expressed
as measurable convergence in independent reconstructions. The ratchet
is the fixation process; the k=3 closure bar is the fixation test (the
genome breeds true across k independent developments in at least two
producer families); the succession gen-2 step is the heredity test
(vertical transmission under an environment the child chose).

Three levels, only the first invariant:

1. **The genetic code** (substrate-free, unchanged since named):
   criterion/candidate/authority separation; seal/verify/audit/rebuild/
   crosscheck; roots only move forward; no agent signs.
2. **The genome** (this document): the pin set at a named root,
   converging toward fixation.
3. **The phenotype** (free): the implementations. Corpus-measured
   2026-10-09: eight realizations, 32 of 37 modules with eight distinct
   AST shapes, family-bimodal (codex ~4.6k lines, claude ~8.5k,
   cross-family similarity 0.123). Carries nothing; inherits nothing.

## The gene table — selected, fixed, expressed

The significant genes, each with the seam that selected it and the
steering evidence since fixation. (The full boundary lineage — all 34
recorded revisions — is in `genome-map.json`; early bundles carried
many small genes each and are summarized there.)

| gene | locus | selected by | fixed | expression / steering since |
|---|---|---|---|---|
| core export contract (41 names) | core | 2026-09-21 assembled rebuild: regrown core dropped private names upper layers import | 2026-09-21 | core.py is the most convergent substantive module (0.377) |
| KINDS vocabulary content | core | silence map: five conforming implementations held five values | 2026-10-03 | folded into core's convergence |
| verdict vocabulary (`broken` et al.) | exchange | r10 era: six words across ten implementations; r9 drew right by luck | 2026-10-07 bundle | matrix rows uniform since |
| glob expansion in `inputs` | authoring | r10 (claude): pack expanded globs in `generated` only | 2026-10-07 (reset #1) | no recurrence r12–r18 |
| the room recipe is TOML | exchange | r12 (claude): wrote canonical JSON into reticuli.toml; self-incompatible at format 3+ | 2026-10-07 (reset #2) | no recurrence r13–r18 |
| room is substance, not form (step-SET equality) | exchange | r11 tree refused by an over-strict canonical-order assertion | 2026-10-08 | an anti-canalization gene: widens the class deliberately |
| deep-audit transitivity (3-claim fixture) | exchange | r4: regrown walkers judged direct components and stopped | 2026-10-05 | all 8 corpus walkers recurse; see unfixed sibling below |
| producer freedom = inheritance (socket probe) | build | r14 halt: the probe asserted absolute network where it meant "no added jail" — an instrument bug, fixed as measured | 2026-10-08 (0482adb5) | build layer first-attempt in r15–r18 |
| pack→audit_deep record round-trip | authoring | r14 (claude): pack sealed `{component, root}`, its audit_deep read `link["input"]` — self-inconsistent | 2026-10-08 (2d102714, reset #3) | **steering confirmed 4/4** (r15–r18 authoring all first-attempt) |
| jail floor, planks 1–6 (/dev sinks, spawn, read-host, uname, …) | run | r4's deny-default jail, then each stricter draw | staged 2026-10-05/06 | behavior pinned; run.py shape stays free (0.116) |
| jail floor, plank 7: user lookup | run | r16 (claude): identity passed, audit_repo failed — deny-default jail refused `pwd.getpwuid` (opendirectoryd mach-lookup) | 2026-10-09 (71fd7559, reset #4) | **steering confirmed 1/1**: r17 run-layer pass AND audit_repo pass → the first claude qualifier |
| format 4 (canonical step order at seal) + room-substance relaxation | recipe/exchange | format-wording divergence across families | 2026-10-06 → relaxed 2026-10-08 | a gene revised after over-expression: pinned substance, released presentation |

Mis-pins averted (selection events that did NOT fix — the discipline
record): the dedup-key diagnosis (r13; withdrawn after measurement
falsified it), the silent-truncation facet (falsified: r13 raises, not
truncates), the nested-staging localized fixture (mechanism isolated,
fixture unencodable — accepted as caught by self_check). A signature
authorizes intent, not a wrong diagnosis.

## Unfixed alleles — staged, not in the genome

| candidate | selected by | status |
|---|---|---|
| flat-store resolution (a flat-staged composed claim must audit deep) | r15 (claude) + r18 (codex) — cross-family, incidence 2/4 draws | **measured** 2026-10-09: fixture passes shipped, bites both walkers. Staged; landing resets the count (would surrender the r17 qualifier). Keyholder paused it. |
| **data-dependency re-earn** (a declared data dependency's content match re-earns at audit) | the corpus performance assay 2026-10-09 — **the first instrument-found seam**; forged pulled-data attribution false-passes verify/audit/audit_deep/deps in EVERY realization, the shipped tool included | **measured**: witness refused by nothing today. Staged; needs a criteria edit AND a src fix together (the 2026-09-28 soundness-closure precedent). |
| **signature depth** (a signature says how deep it looked) | instrument sweep 2026-10-09 — sign re-earns only the shallow audit; a deep-broken composed claim is SIGNED while sign_root folds its chain into signed identity (witness measured) | staged; a DESIGN decision (statement-names-depth vs deep-by-default) for the keyholder |
| copy compactness (one physical copy per dependency) | the 23G `.selfclaim` unfolding; compact-deps landed as implementation 2026-10-08 | forward pin; trigger = deep chains routine |
| author-at-format-4 (pack's default for fresh claims) | cross-judging 2026-10-05 | optional; off the trial path |

## The expression track — corpus convergence per locus

Mean pairwise similarity among the seven complete regrown trees
(r9, r11, r18 codex; r14–r17 claude), 2026-10-09. Convergence tracks
pin density; every seam to date occurred at a low-convergence locus.

```
LOCUS                          CONV    NOTES
_kernel/core.py                0.377   most-pinned substantive locus (export contract, KINDS)
feedback.py                    0.244
_kernel/seal.py                0.238
_kernel/attest.py              0.216
_kernel/recipe.py              0.209
_kernel/identity.py            0.197
_util.py                       0.182
hooks.py                       0.144
transfer.py                    0.140
reference.py                   0.134
_cli/output.py                 0.131
pack.py                        0.117   seam site: r14 (record round-trip)
_kernel/run.py                 0.116   seam site: r4 floor, r16 (user lookup)
attest.py                      0.114
_cli/handlers.py               0.111
assess.py                      0.110
render.py                      0.104
record.py                      0.102
authoring.py                   0.099
_kernel/crosscheck.py          0.090
_cli/parser.py                 0.088
_cli/views.py                  0.084
reuse.py                       0.075
launcher.py                    0.067
_cli/statusview.py             0.066
_kernel/build.py               0.064
kernel.py                      0.061
registry.py                    0.060   seam site: r13, r15, r18 (staging/resolution)
_cli/report.py                 0.057
heldout.py                     0.049
_cli/verbs.py                  0.046
_cli/dispatch.py               0.024   least canalized locus in the tree
(glue files __init__/__main__/cli.py omitted: 0.58–0.76, trivially convergent)
```

Reading: HIGH convergence = genetically determined (the criteria force
it). LOW convergence + no seam history = either genuinely free (the
class's intended width) or unexercised risk. LOW convergence + seam
history (registry, run, pack) = the loci where the genome has been
learning. Forward, falsifiable: if the recursion ever exercises the
bottom of the table hard (dispatch, verbs, report, heldout), that is
where the next seams live.

## The articulation reading — is the root on target?

Selection events per boundary era are not yet slowing: four of the
twelve table genes fixed in the last three days, and one measured
allele is staged. The curve is still rising, BUT its character changed
at r16/r17: the claude seams moved from the tool-as-content surface
(six seams) to the tool-as-auditor surface (one seam), and the first
draw after that pin qualified. Surfaces appear enumerable (produce,
judge, orchestrate — the gen-2 step already exercises the third).
Operationally, "on target" = the existing fixation test passes: k=3
qualifying trials, two families, no intervening fixation. Count at
this writing: 1 of 3 (r17) at `71fd7559`, with one measured allele
deliberately held un-fixed by the keyholder.

## Regenerating this map

Corpus assay: the centroid analysis (8 realizations × 37 modules,
byte/AST/similarity). Mutation log: `research/provenance/revision-*.md`
(34 records; harvested into genome-map.json). Fossil record:
`research/metrics/closure-ledger.md`. Re-run the assay and re-emit this
document at each boundary version; the diff between versions is what
the genome learned.
