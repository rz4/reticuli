# Open issues before submission

Blocking items are marked **[BLOCK]**: the manuscript should not be
submitted with these unresolved, because a reviewer who checks will find
a claim the repository does not support. Everything else is a quality
item.

## 0. Resolved by the independent review of 2026-10-12

Two of these were factual errors in the manuscript, not presentation
problems. Both are corrected; the corrections are recorded here because
the numbers appeared in a committed draft.

**Corpus accounting (was wrong).** The draft reported "the three agree
on 332 and disagree on 149" of 522 cases, leaving 41 cases unaccounted
for. Recomputed from `baseline.json`: all three return the same verdict
on **373** --- 332 passed by all three, 41 failed identically by all
three --- and differ on **149**. The headline 28.5% disagreement figure
is unaffected. The error was inherited from `PHASE0.md`, which labels
agreement-and-passing as "three-way agreement". That project document
should be corrected too.

**The recursive step (was overstated).** The draft said the third trial
"produced a further generation, recorded as landing the identity
`4c2abcbf`". That identity is the **core-layer scaffold root**, not a
whole-system identity: `lineages-g2/codex/ledger.jsonl` records it as
the `core` layer's `scaffold_root`. The recursive step exports, rebuilds
and verifies **one component claim**. It establishes that a
reconstruction can drive the export/rebuild/verify path; it does not
establish that a fourth complete system was grown. Corrected in §7.1,
Figure 3, the appendix, the findings table and the evidence map.

**The admissibility condition (was formally wrong).** The draft stated
Condition 2 as "equivalently $\Pi(S) \subseteq \mathrm{Sem}(S)$" and
described the gap between the read set and the semantic content as
designer freedom. Condition 2 as stated admits no such gap: material
that cannot change a verdict must not be committed whether or not it is
meaningful. The correct bound is $\Pi(S) \subseteq \mathrm{Rd}(A,S)$,
so the two conditions together give $\Pi(S) = \mathrm{Rd}(A,S)$ exactly.
The section now separates three notions the earlier text conflated ---
semantic relevance, acceptance relevance, and producer guidance --- and
states that guidance lies in $\mathrm{Sem} \setminus \mathrm{Rd}$ and is
therefore excluded automatically. The practical consequence is unchanged
and in fact sharper: the committed set is not a design parameter, so the
only repair to a determination failure is to shrink what the judge can
read.

Also addressed in the same pass: determination's three assumptions
(deterministic acceptance under a fixed environment, collision
resistance) are now explicit; the probe-population confound is now a
named threat; textual dissimilarity is now distinguished from
algorithmic diversity; the protocol's incompleteness is stated in the
abstract, the contributions list and Figure 1 rather than only in §9;
"requirements determine the software" is replaced throughout by
"sufficient to obtain a conforming implementation"; an accounting table
reconciles the 26/8/7/3 populations; and the artifact citation pins an
immutable snapshot.

## 0a. Resolved by the second review of 2026-10-12

**The admissibility condition was still wrong after the first fix.** The
first revision replaced $\Pi \subseteq \mathrm{Sem}$ with
$\Pi = \mathrm{Rd}$, which is the right design goal but does not
establish Condition 2 as it was then stated. The reviewer's
counterexample is decisive and elementary: adding a comment to a
committed acceptance program changes no verdict and leaves the read set
identical, yet changes the bytes at a committed path and therefore the
identity. Both $\Pi$ and $\mathrm{Rd}$ are sets of *paths*; the
variation in question is *within* a path, so no choice of committed
paths can deliver invariance. The stronger property would require
canonicalizing programs up to semantic equivalence.

Condition 2 is now stated as invariance under changes to *excluded*
paths, which holds by construction, with $\Pi = \mathrm{Rd}$ demoted
from a theorem to the design goal that maximizes what the identity
ignores. The residue is stated explicitly, and the project's own history
supplies the instance: a comment-only change moved an identity and
invalidated an already-qualifying trial, which was regrown. The two
witnesses are reframed as *partial* canonicalization of known,
finitely-describable structure, which is what they actually are.

**Randomized acceptance was not in the formalism.** Equation (1) defined
the admitted set without reference to the seed, while §5.2 requires
fresh entropy per evaluation. Acceptance is now written
$A_S(P; e, \omega)$, the admitted set is defined as passing for all
$\omega$ and flagged as unobservable, and the text distinguishes a
per-run verdict from a claim about future audits. We decline to estimate
a pass probability, having too few draws per implementation.

**The lookup-table exclusion was categorical and is now economic.**
Generated-input obligations do not categorically exclude table-based
strategies. They make memorizing the fixed corpus insufficient and force
any table to cover the generator's reachable input space. An
implementation that memorized the generator would still defeat them.

**The cost envelope conflated zero measured spend with zero cost.** Both
families ran on flat-rate subscriptions and recorded zero metered
expenditure against a \$40 ceiling, which by the protocol's own
three-valued rule should read incomplete rather than satisfied. §3 now
says so and identifies it as a defect in our implementation of the
protocol: the declared ceiling should fall back to the strongest unit
actually measured. **Not yet fixed in the code.**

**Editorial.** The conclusion now states that the subsequent
reconstruction rebuilt one component. The diversity population is now
consistently described as seven independent reconstructions plus the
shipped implementation as a reference point, with similarity computed
over the seven.

## 0b. Added by the review, not yet done

**[BLOCK for a selective venue] A baseline comparison.** The review is
right that the paper establishes a new way of discovering
underspecification without establishing its relative efficiency. The
argument now in §2.3 --- that differential testing can find the
divergences but cannot find a degenerate implementation that does not
yet exist --- bounds the comparison but does not substitute for it. A
controlled study should measure defects found, distinct failure classes,
wall-clock and token cost, and human adjudication time, for
reconstruction against differential and property-based testing on the
same target.

**Functional diversity metrics.** Textual dissimilarity establishes that
reconstructions are not copies. It does not establish algorithmic
diversity. Candidate measures: behavioral clustering on the probe
battery, control-flow or call-graph distance, mutation-kill profile
overlap. None applied.

**A held-out probe design for repair measurement.** See §2 below; the
review independently identified this as the strongest available fix for
the adaptive-analysis threat.

**Fall the cost envelope back to a measured unit.** A code change, not
a paper change: a declared monetary ceiling compared against a flat-rate
run's zero should yield \textsf{incomplete}, not \textsf{accept}. This
is the only item on this list that is a defect in the system rather than
a gap in the evidence.

**Machine-readable experimental manifests.** The review asks for raw
trial metadata and manifests alongside the prose records. The sealed
trial claims are machine-readable; the ledgers and revision records are
prose. Emitting a single manifest per trial would close this.

## 1. Evidence gaps

**[BLOCK] The failure-per-generation series (3, 3, 3, 2, 1, 0).**
Section~7.2 reports this as the authors' classification, which is honest
but weak for what it is being asked to support: it is the self-hosting
arm's main quantitative evidence for RQ4. Either derive it mechanically
from the 34 recorded revision files with the counting rule stated, or
demote it from a series to a qualitative statement. Deriving it is
probably a day's work and would materially strengthen §7.2.

**[BLOCK] Held-out battery provenance.** The figure `104/104` recurs
across seven trials, and the manuscript describes the battery as
deliberately outside the committed identity. Before submission, record
when the battery was written relative to the trials and whether it was
ever revised in response to a trial failure. If it was revised after
seeing failures, it is not held out in the strong sense and both §7.1 and
the appendix must say so.

**The 23 GB figure.** Stated in §7.2 as "approximately 23 GB for a
20-layer chain in ordinary use". This was a disk observation during
development, not a logged measurement. Either reinstate the defective
copy procedure and measure it, or keep the approximation and never give
it a decimal. Currently handled correctly in the text; do not let a
later edit sharpen it.

**Cost figures.** Both producer families ran on flat-rate plans, so the
repository's dollar ledgers understate market cost. The appendix says
this. Do not add a cost-per-reconstruction figure anywhere without a
metered measurement behind it.

## 2. Statistical and methodological

**[BLOCK] Adaptive analysis on the jq contraction.** The paired
per-probe analysis was specified *after* the aggregate analysis failed.
The manuscript discloses this in §9. That disclosure is necessary and may
not be sufficient for a methods-attentive reviewer. The strongest
available fix is to run the paired analysis on a boundary pair the
analysis has never seen — the pending election revision would provide
exactly this, and the cross-family prediction in §7.4 is already
recorded in advance. If that revision lands before submission, add it as
a confirmatory test and the adaptive-analysis threat largely dissolves.

**Unit of observation.** Probes within a sample are not independent: they
come from one seeded battery, and a single implementation defect moves
many at once. The manuscript reports exact tests on the paired per-probe
unit and calls the result exploratory. Consider reporting a
sample-level permutation test as a robustness check, which would be
immune to the within-sample dependence.

**n = 1 on the claude leg.** The negative cross-family result rests on a
single sample per boundary. This is stated. One more claude sample at
each of `S_1` and `S_2` would turn a suggestive negative into a
measured one, at roughly three hours of wall-clock each.

**Confidence intervals.** The manuscript gives point estimates and exact
tests. Add a Clopper-Pearson interval for the 6/6 and 0/6 consumer
substitution rates, which are small-n proportions carrying real weight
in §7.3.

## 3. Comparative claims

**No baseline was run.** §9 limits the comparative claims accordingly,
and this is the right call given no new experiments. A reviewer will
still ask whether ordinary differential testing against `gojq` and `jaq`
would have found the same jq defects more cheaply. The honest answer is
probably "yes for the divergences, no for the lookup table", since the
memorization failure is only visible when you *generate* an
implementation. Consider stating that argument explicitly in §2.3 or
§8.2 rather than leaving the reader to construct it.

## 4. External reproduction

**[BLOCK for the strongest framing] No external operator receipt.**
Every self-hosting result is laboratory-only, which §9 states plainly and
the consolidated findings table marks per row. The paper is submittable
in this state as long as the framing holds. If a receipt arrives before
submission, §7.1, §7.5 and §9 all change, and the protocol's own M2 leg
stops being incomplete for its headline result. This is the single
highest-value outstanding item and it is not a compute task; it needs a
person outside the project to run one audit command.

## 5. Formal content

**Proposition 1 is the only formal statement and it is trivial.** This is
acknowledged in the text by calling it trivial as mathematics. The two
identity conditions (determination, admissibility) are stated as
conditions with witnesses rather than theorems, which is appropriate
given that the read set is an operational quantity. If a reviewer asks
for more formal weight, the available candidate is the composition
result: acceptance of a composite is not determined by the acceptances
of its parts, because each part's identity names a class rather than the
member actually linked. That is currently prose in §4.3 and could be
stated as a proposition with the three forgeries as its witnesses.

**Determination's read set is not decidable.** The manuscript's
conditions are stated over an operational read set, approximated by
construction (materializing only committed bytes into the judging
context) rather than by analysis. This is sound for the resulting system
and yields no decision procedure for an arbitrary one. Currently implied
but not stated; add one sentence to §4.2.

## 6. Production

**Figure legibility.** Figures 1 and 4 are two-column floats; Figures 2
and 3 are single-column. The brief prefers single-column where legible.
Figure 1 was tried at column width and is too dense; the current
two-column version is the right call. Re-check at print size before
submission.

**Figure 4 is hand-plotted.** Bar heights and error bars are computed in
TikZ from the numbers in `rate_comparison.json` and
`rate-metric-findings.md`, not generated from the data file by a script.
Values were checked by hand against those files. For an artifact-track
submission, consider emitting the TikZ coordinates from the JSON so the
figure is mechanically tied to its data.

**Reference verification.** `references.bib` contains 38 entries, all
real publications, with DOIs where available. Before submission, verify
each against the publisher record; the entries most worth double-checking
are the ones cited from memory of venue and year rather than from a
retrieved record: `mckeeman1998` (Digital Technical Journal volume and
pages), `chen1998` (the technical report number), `alur2013` (FMCAD page
range), and the arXiv identifiers on the generative-SE entries.

**Terminology sweep.** The repository uses a biological register (gene,
genome, phenotype, fixation, domestication, speciation). The manuscript
uses none of it; `evidence-map.md` §8 holds the translation table. If
text is imported from repository documents during revision, re-run that
sweep.

## 7. Items deliberately excluded

Recorded so they are not mistaken for omissions.

- **The economic analysis is hypotheses only.** §8.3 names four
  measurable quantities and claims none of them. This is per the brief;
  do not let a revision add a savings figure.
- **Recursive self-improvement is explicitly disclaimed.** §8.4 states
  that every adopted obligation required human authorization, that three
  diagnoses were wrong and caught only by measurement, and that a
  producer improving its own boundary has no external check.
- **Legal questions are flagged, not resolved.** §8.5 distinguishes
  technical reconstructability from the right to reproduce, and states
  that the legal treatment of behavioral reimplementation is outside the
  authors' competence.
- **No new experiments were run for the manuscript.** Stated in the
  artifact availability section and in Table 1's caption.
