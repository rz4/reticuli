"""Per-program divergence RATE: the instrument the aggregate count failed to be.

For every (program, input) probe, the rate is the fraction of samples at
a boundary that diverge from reference jq there. Unlike the aggregate
count, a rate is stable under sample-to-sample variation: one unlucky
sample moves a rate by 1/n, not by its whole divergence budget.

Comparing boundaries then becomes a paired, per-probe comparison — the
same probe before and after a repair — which is both more sensitive and
honest about WHICH silence closed.

    python3 rate_metric.py            # all boundaries found
    python3 rate_metric.py S_1 S_2    # paired comparison
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "baseline")

# which sample files belong to which boundary (the jq ledger's record)
BOUNDARIES = {
    "S_1": ["probes_g2_sample1.json", "probes_g2_codex_s2.json",
            "probes_g2_codex_s3.json"],
    "S_2": ["probes_g3_codex_s1.json", "probes_g3_codex_s2.json",
            "probes_g4_ctl_s1.json", "probes_g4_ctl_s2.json",
            "probes_g4_ctl_s3.json"],
}
# claude samples are kept out of the rate comparison: family is a
# confound, and only S_1 has one.


def load(boundary):
    """{probe_key: set(sample files that diverged)} plus the sample count."""
    files = [f for f in BOUNDARIES[boundary]
             if os.path.isfile(os.path.join(BASE, f))]
    extra = [f for f in sorted(os.listdir(BASE))
             if f.startswith("probes_") and f.endswith(".json")
             and f not in sum(BOUNDARIES.values(), []) and "claude" not in f]
    if extra and boundary == "S_2":
        files += extra          # later powered samples land here
    div = defaultdict(set)
    for fn in files:
        for r in json.load(open(os.path.join(BASE, fn))):
            div[(r["i"], r["program"], r["input"])].add(fn)
    return div, len(files), files


def rates(boundary):
    div, n, files = load(boundary)
    return {k: len(v) / n for k, v in div.items()}, n, files


def main():
    which = sys.argv[1:] or ["S_1", "S_2"]
    table = {}
    for b in which:
        r, n, files = rates(b)
        table[b] = r
        always = sum(1 for v in r.values() if v == 1.0)
        print(f"{b}: {n} samples ({len(files)} files)  "
              f"probes with any divergence: {len(r)}  "
              f"ALL samples diverge: {always}  "
              f"mean rate over divergent probes: "
              f"{sum(r.values()) / max(len(r), 1):.2f}")
    if len(which) != 2:
        return 0
    a, b = which
    ra, rb = table[a], table[b]
    keys = set(ra) | set(rb)
    closed = [k for k in keys if ra.get(k, 0) >= 0.66 and rb.get(k, 0) == 0.0]
    opened = [k for k in keys if ra.get(k, 0) == 0.0 and rb.get(k, 0) >= 0.66]
    held = [k for k in keys if ra.get(k, 0) >= 0.66 and rb.get(k, 0) >= 0.66]
    print(f"\nPAIRED per-probe comparison {a} -> {b} "
          f"(consistent = diverging in >=2/3 of samples):")
    print(f"  CLOSED (consistent at {a}, never at {b}): {len(closed)}")
    print(f"  HELD   (consistent at both):              {len(held)}")
    print(f"  OPENED (never at {a}, consistent at {b}): {len(opened)}")
    net = len(closed) - len(opened)
    print(f"  net closure: {net:+d} probes")
    # the sum of rates is the expected divergences per sample: a rate-based
    # aggregate that does not depend on how many samples were drawn
    ea = sum(ra.values())
    eb = sum(rb.values())
    print(f"\nEXPECTED divergences per sample (sum of rates): "
          f"{a}={ea:.1f}  {b}={eb:.1f}  change {(eb - ea) / ea:+.1%}")
    json.dump({"boundaries": {k: {"probes": len(v)} for k, v in table.items()},
               "closed": len(closed), "held": len(held), "opened": len(opened),
               "expected_per_sample": {a: ea, b: eb}},
              open(os.path.join(BASE, "rate_comparison.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
