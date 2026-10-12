# Open issues before submission

Blocking items are marked **[BLOCK]**: the manuscript should not be
submitted with these unresolved, because a reviewer who checks will find
a claim the repository does not support. Everything else is a quality
item.

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
