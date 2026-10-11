"""Score a generation against the preregistration: P1 recall, P2
enrichment, P3 novelty candidates. Pools every probes_g*_*.json sample
file against the frozen H-shadow (oracle_splits.json).

A probe is identified by (case index, program, input) — the same
deterministic coordinates every sample and the shadow share."""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "baseline")


def key(row):
    return (row["i"], row["program"], row["input"])


shadow = json.load(open(os.path.join(BASE, "oracle_splits.json")))
shadow_keys = {key(s) for s in shadow}
shadow_by_key = {key(s): s for s in shadow}

samples = {}
for fn in sorted(os.listdir(BASE)):
    if fn.startswith("probes_g") and fn.endswith(".json"):
        samples[fn] = json.load(open(os.path.join(BASE, fn)))

print(f"H-shadow: {len(shadow_keys)} human-split probes of 1395 "
      f"({len(shadow_keys) / 1395:.1%} base rate)")
print(f"samples pooled: {len(samples)}\n")

pooled = {}
for fn, rows in samples.items():
    hit = sum(1 for r in rows if key(r) in shadow_keys)
    print(f"  {fn:34} M={len(rows):4}  on-shadow={hit:4} "
          f"({hit / max(len(rows), 1):.0%})")
    for r in rows:
        pooled.setdefault(key(r), []).append((fn, r))

print()
# ---- P1: recall over the pooled generation
covered = [k for k in pooled if k in shadow_keys]
print(f"P1 RECALL  pooled M={len(pooled)} distinct probes; "
      f"of the {len(shadow_keys)} human-split probes, "
      f"{len(covered)} were surfaced = {len(covered) / len(shadow_keys):.1%}")

# ---- P2: enrichment
enrich = (len(covered) / len(pooled)) / (len(shadow_keys) / 1395)
print(f"P2 ENRICH  {len(covered)}/{len(pooled)} = "
      f"{len(covered) / len(pooled):.1%} of pooled M lies on human-split "
      f"probes vs {len(shadow_keys) / 1395:.1%} base rate -> {enrich:.2f}x")

# ---- P3: novelty candidates — value divergences OFF the shadow,
# agreed by MULTIPLE independent samples (one sample could just be wrong)
multi = {k: v for k, v in pooled.items() if len(v) >= 2}
off_shadow_multi = {k: v for k, v in multi.items() if k not in shadow_keys}
value_div = {k: v for k, v in off_shadow_multi.items()
             if any(r["sample"] == "ok" and r["jq"] == "ok" for _, r in v)}
print(f"\nP3 CANDIDATES (>=2 independent samples, OFF the human shadow)")
print(f"  multi-sample divergences:        {len(multi)}")
print(f"  of those, off the shadow:        {len(off_shadow_multi)}")
print(f"  of those, both-ok value splits:  {len(value_div)}  <- novelty leads")
for k, v in list(value_div.items())[:10]:
    print(f"    [{len(v)} samples] {k[1][:66]!r} on {k[2][:40]!r}")

print("\nagreement structure (how many samples flagged each probe):")
print("  ", Counter(len(v) for v in pooled.values()).most_common())

# programs most often divergent across samples: the silence map's hot spots
print("\nhot programs (flagged by probes across all samples):")
for p, n in Counter(k[1][:58] for k in pooled).most_common(12):
    print(f"  {n:3}  {p!r}")
json.dump({"pooled": len(pooled), "covered": len(covered),
           "shadow": len(shadow_keys), "enrichment": enrich,
           "p3_leads": [{"program": k[1], "input": k[2],
                         "samples": [f for f, _ in v]}
                        for k, v in value_div.items()]},
          open(os.path.join(BASE, "generation_score.json"), "w"), indent=1)
