"""Compare a main-behaviour run to a ret/2 run, schema-aware.

The branch changes the file's shape on purpose (A66 logs the warmup
evaluations; A31 adds transfer-row event ids), so (step, value) digests
cannot be the instrument. Instead every series is classified:

  wall-clock      _time/_flops suffixes; differ between any two runs
  identical       same value sequence (step labels may shift)
  prefix-added    v2 = [new leading rows] + original   (A66's signature)
  rows-inserted   original is an ordered subsequence of v2 (A31's signature)
  DIFFERENT       anything else -- the only category that indicts the branch
"""
import csv, sys
from collections import defaultdict

def series(path):
    out = defaultdict(list)
    rows = list(csv.reader(open(path, newline="")))
    head = rows[0]
    si, mi, vi = head.index("step"), head.index("metric"), head.index("value")
    for r in rows[1:]:
        if len(r) == len(head):
            out[r[mi]].append(r[vi])
    return out

def is_subseq(small, big):
    it = iter(big)
    return all(x in it for x in small)

a, b = series(sys.argv[1]), series(sys.argv[2])   # a=original, b=v2
cats = defaultdict(list)
for name in sorted(set(a) | set(b)):
    va, vb = a.get(name), b.get(name)
    if va is None: cats["only-in-v2"].append((name, len(vb))); continue
    if vb is None: cats["only-in-original"].append((name, len(va))); continue
    if name.endswith(("_time", "_flops")):
        cats["wall-clock"].append((name, "")); continue
    if va == vb:
        cats["identical"].append((name, f"{len(va)} values")); continue
    k = len(vb) - len(va)
    if k > 0 and vb[k:] == va:
        cats["prefix-added"].append((name, f"+{k} leading")); continue
    if k > 0 and is_subseq(va, vb):
        cats["rows-inserted"].append((name, f"+{k} inserted")); continue
    nd = sum(1 for x, y in zip(va, vb) if x != y) + abs(len(va) - len(vb))
    cats["DIFFERENT"].append((name, f"{nd}/{max(len(va), len(vb))} differ"))

for cat in ("identical", "prefix-added", "rows-inserted", "wall-clock",
            "only-in-v2", "only-in-original", "DIFFERENT"):
    rows = cats.get(cat, [])
    print(f"{cat:<18} {len(rows)}")
    if cat in ("prefix-added", "rows-inserted", "only-in-v2",
               "only-in-original", "DIFFERENT"):
        for name, why in rows:
            print(f"    {name:<44} {why}")
