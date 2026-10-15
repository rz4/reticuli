# Methods appendix: floor probes and per-side cost accounting

2026-10-15. Companion to `scientific-capability-acquisition.md`, replacing
two of its planning assumptions with protocols that were run this week on
reticuli itself, through the DOE Model Access Gateway, with the numbers
attached. Where the proposal says "provider selection can be treated as a
cost-constrained experimental design problem" (§7.4) and "compute
expenditure should be recorded by capability-acquisition event" (§17.3),
this document says how, and what it measured.

Numbers marked *interim* were read while runs r28/r29 were still finishing;
the succession harness ledgers are the durable record.

## A. The floor-probe protocol

### The problem it solves

A reconstructor below some capability threshold contributes zero
acquisition yield at full cost. The threshold is not knowable from model
cards: it depends on what the acceptance criteria actually demand. Buying
full reconstruction runs to discover it is the most expensive possible
instrument for the question.

### The protocol

1. **Find the discriminating criterion.** Run one cheap producer to
   failure. The layer (or criterion) where it halts is, by construction,
   the first obligation that separates producers. For reticuli this was
   the identity layer — the first check demanding exact byte-level
   serializations re-derived from prose. A free-tier model (gemma-4)
   located it for $0: two layers cleared in 28 seconds each, then three
   40-turn attempts failed on the third.
2. **Preregister the split.** Before probing, commit predictions naming
   which producers clear and which fail (`predictions_r29.md`). A floor
   located after the fact is a story about the results.
3. **Probe, don't run.** Grow only through the discriminating criterion
   (`--stop-after 3` here: the two layers below it, then the
   discriminator). Hold the per-attempt budget FIXED at whatever the
   qualifying producers had (40 tool-use turns here) — raising it for a
   weaker model measures patience, not capability.
4. **Void, don't count, infrastructure stops.** A quota or rate-limit
   event voids that producer's probe rather than scoring as a failure.
   A throttled producer misread as an incapable one corrupts the floor
   silently.
5. **Spend only on clears.** A probe that clears the discriminator earns
   a full reconstruction run. Nothing else does. Clearing is necessary,
   not sufficient: reticuli's r26 grew all 21 layers with a frontier
   producer and still failed the assembled gate.

### Measured results (2026-10-15, root 3302eb8a)

| producer | $/Mtok in,out | identity | probe cost (last attempt, observed) |
|---|---|---|---|
| gemma-4-thinking (free) | 0, 0 | failed x3 | $0 |
| gpt-oss-120b | 0.15, 0.60 | failed x3 | $0.014+ |
| nemotron-super-3 | 0.15, 0.65 | failed x3 | $0.091+ |
| gpt-6-luna:high | 0.10, 0.50 | *interim: attempt 2* | $0.015+ |
| claude-haiku-5-5:high | 0.10, 0.50 | **cleared** | $0.037 |
| mistral-large-3 | 0.50, 1.50 | **cleared** | $0.560 |
| gemini-3.8-flash:high | 0.75, 3.75 | *interim: attempt 1, after 3 tries at recipe* | — |

Observed costs are floors, not totals: the harness wipes a failed
attempt's room, so only the final attempt's usage file survives (bounded
below 3x for a three-attempt failure). Even at that bound, locating the
floor across seven producer families cost **under $3 total**, versus
roughly $5-15 per full reconstruction run — and the preregistered split
was two-thirds right and wrong in the informative direction (mistral,
called as a coin-flip, cleared; it is the cheapest frontier-adjacent
clear in the table).

The floor is now bracketed: above gemma-4, nemotron-super-3 and
gpt-oss-120b; at or below claude-haiku-5-5 and mistral-large-3. The
proposal's scheduler (§7.4) should spend its reserved-diversity budget on
probes at this granularity before allocating reconstruction work.

### A domain-specific prediction for the scientific program

The criterion that kills sub-frontier producers in reticuli demands exact
bytes. Scientific operators (§8.3) are specified with tolerance bands, and
tolerance-banded criteria are plausibly EASIER to reconstruct from than
byte-exact ones. If so, the capability floor for scientific instruments
sits lower than reticuli's own, and the heterogeneous population is
cheaper in that domain than in this one. This is testable in WP3 with the
same protocol and should be one of its first measurements.

## B. Per-side cost accounting

### The defect it replaces

The producer originally reported one total token count, priced at the
midpoint of the input and output rates. Measured against a live run, that
is not an approximation but a systematic error: the agentic producer's
shape is **94% input** (it re-reads the whole acceptance check every
turn — 858,685 input vs 58,132 output tokens on one measured attempt), and
gateway rates differ by 5x between sides and up to 20x once a provider
serves the re-read prompt from cache. The blended figure overstated a
measured attempt by 2.2x fresh and 5.4x cached. For a program whose
central hypotheses (H1, efficiency(g)) divide by total amortized cost, a
5x systematic error in the denominator decides hypotheses by accounting.

### The contract

Every producer-side usage record carries:

- `calls` — API round trips (a rebuild is not one call; a measured
  identity attempt was 40),
- `input_tokens`, `output_tokens`, `cached_input_tokens` — the three
  separately-priced goods, never pre-summed,
- `usd` — computed as `in*r_in + out*r_out + cached*r_cache`, in dollars
  per million tokens,
- `usd_rates` — the three rates used, written BESIDE the total, so the
  dollars are recomputable by a reader who trusts nothing. A figure
  nobody can recompute is a number, not a measurement.

Rules, each forced by an observed failure mode:

1. **No rate quoted for cache reads → cached tokens are charged as fresh
   input.** Overstating a cost is a safer default than hiding one.
2. **No price quoted at all → no `usd` key.** An unpriced run reports
   tokens and sits honestly one rung down the cost-evidence ladder
   (usd > tokens > calls > wall-clock) rather than guessing.
3. **Junk or non-finite rates ("nan", "inf", negative) → no `usd` key.**
   A cost that is not a finite nonnegative number is not a cost. (This
   mirrors a criterion signed into reticuli's root on 2026-10-15 after a
   reconstruction trial forced it.)
4. **Reasoning tokens are not added separately** — providers bill them
   inside output; counting both double-charges.

### What it measured on day one

- Prompt caching is real and provider-dependent: claude-haiku via the
  google provider served 308,586 of 448,035 prompt tokens (69%) from
  cache; the amazon and cborg providers reported no cache detail at all,
  so rule 1 priced them conservatively.
- The calls count exposed what a per-rebuild "1 call" assumption hid:
  failed acquisition attempts are where the round trips concentrate
  (43 observed calls across a halted lineage's surviving records).

### What the proposal should take verbatim

§17.3's category list is right but under-specified by one level: each
category's records need the four fields and four rules above, or the
marginal-value analysis it promises will inherit the 2-5x error this
section was written to remove. §7.3's per-contribution cost field should
be the same record, not a separate convention.

## C. Smaller carryovers from the same week

- **Feedback placement (for the SVG):** an obligation checked only at
  assembly is sound and nearly useless as feedback — reticuli's r26
  producer wrote one defective function, passed its layer, and learned of
  the refusal four hours later at assembly. The Scientific Validation
  Gate must stay the authority, but layer-local scientific checks (units,
  conservation on a toy case) belong INSIDE the acceptance criteria
  implementers build against. The equivalent correction was signed into
  reticuli's root on 2026-10-15.
- **Positive controls for challenge batteries:** zeta's coverage report
  refuses to exist unless a mutant that should survive still survives.
  An SVG without a known-wrong instrument it demonstrably rejects makes
  an unfalsifiable claim about itself.
- **Three-valued verdicts:** accept / reject / incomplete, where an
  unmeasured declared condition never accepts. "Not yet validated in
  regime X" must be distinguishable from both "validated" and "failed",
  or §9.2's operating-domain restrictions erode silently.
- **Criterion authorship is a role:** §13.4's "a behavioral specification
  is frozen" needs an author, and if the proposer authors both criteria
  and candidate, reconstruction agreement measures shared lineage, not
  independence. Make criterion-author a distinct §7.1 role and keep a
  foreign-specification control arm (reticuli's is the jq family:
  three independent implementations of a spec authored by somebody else).
