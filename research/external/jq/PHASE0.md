# jq arm, phase 0 — the feral population, frozen and measured

*2026-10-11. Materials and baseline only; no rooms opened, no model
spend. The experiment proper begins after the preregistration is signed
(design: research/design/jq-negative-space-experiment.md).*

## Frozen materials (SHA256SUMS beside each)

- corpus/jq-1.8.1.test (522 parseable cases) + man-1.8.1.test — the
  official corpus, S_0's source.
- oracles/: gojq and jaq READMEs (the documented human divergences — H,
  frozen at experiment start), VERSIONS (jq-1.8.1, gojq 0.12.19,
  jaq 3.1.1 — the oracle binaries, which stay OUTSIDE S forever).

## The baseline (baseline/run_baseline.py → baseline.json)

Every corpus case against all three implementations, output-normalized:

    three-way agreement           332 / 522
    cases where the three DISAGREE 149 / 522   (28.5%)
    per-tool corpus pass           jq 479, gojq 408, jaq 337

Nature already ran the control: more than a quarter of jq's OWN
official test corpus is disagreement territory among the three
independent human implementations. The official boundary is incomplete,
measurably — the experiment's premise, confirmed for free. Harness
caveat, stated: ~43 cases fail even for reference jq under the plain
runner (special flags/driver assumptions); these are harness artifacts
to exclude from scoring, and the runner improves before S_0 is carved.
