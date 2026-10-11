# jq generation 2 — the first real evaluator, and the silence map it drew

*2026-10-11. Sample 1 of generation 2, codex, blind room at S_1 root
05c83a25a405 (the law gate). Sample destroyed after measurement per
design; measurements kept (baseline/probes_g2_sample1.json).*

## The law pin steered

Where generation 1 produced a lookup table, generation 2 — one signed
repair later — produced an 869-line streaming JSON filter interpreter
with 100-digit decimal arithmetic and no observation tables. It passed
all 465 corpus cases AND the sixteen entropy-seeded laws, landed the
root, and evaluates novel inputs correctly. One boundary repair
converted the class's cheapest member from memorization to mechanism.

## The measurement (1,395 novel probes × 4 implementations)

    sample agrees with reference jq     1316 / 1395  (94.3%)
    M (divergences from reference)        79
      sample ok, jq errors                37   (error-behavior region)
      both ok, DIFFERENT VALUES           30   (semantic divergences)
      sample errors, jq ok                11
      timeout                              1

**Concentration (P2): supported.** Of M's 79 probes, 47 (59%) are
probes where a HUMAN implementation also splits from reference jq —
against a 21.2% base rate (296/1395): a 2.8× enrichment. Sampled
silence lands where human teams actually disagreed. And M's program
map reads like the divergence literature's table of contents: try/catch
error VALUES, path/setpath/del on edge paths, contains("") and null
bytes, join on heterogeneous arrays, @uri/@html escaping, negative-index
slices — the regions gojq's and jaq's own notes name.

**Recall (P1): accruing, not yet scored.** One sample of the
generation's planned cardinality; M∩H builds across samples. 47
human-split probes covered by one draw is the first installment.

**Novelty (P3): open.** The 30 value-divergences are the hunting
ground; each needs the confirmation step (a counterexample where
reference jq and a human implementation disagree in fact, outside H's
documented notes). Next samples first — novelty candidates compound
across draws.

## Next

More generation-2 samples (same-cardinality codex, then the claude leg
within the keyholder's envelope); then P1/P3 scoring over the pooled M;
then the generation's divergences become staged S_1 → S_2 repairs, each
a signed root move on the jq ledger — the contraction curve's first
step.
