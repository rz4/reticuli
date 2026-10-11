"""The H-shadow: every probe where a human implementation splits from
reference jq, over the same deterministic probe set the samples face.
This is the recall denominator (P1) and the adjudication base (P3) —
oracle-only, no sample involved. Deterministic by the same seeds."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "baseline"))
from run_baseline import parse_cases
import random
import subprocess


def gen_value(rng, depth=0):
    r = rng.random()
    if depth > 2 or r < 0.25:
        return rng.choice([None, True, False, 0, -1, 7, 1e308, -0.0,
                           2**53, 2**53 + 1, 0.1 + 0.2, "", "a", "xy",
                           "null", "0", " ", " x"])
    if r < 0.5:
        return round(rng.uniform(-1e6, 1e6), rng.randint(0, 6))
    if r < 0.75:
        return [gen_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {rng.choice(["a", "b", "k", "x y", "e", ""]): gen_value(rng, depth + 1)
            for _ in range(rng.randint(0, 4))}


def run(argv, prog, inp):
    try:
        r = subprocess.run(argv + [prog], input=inp, text=True,
                           capture_output=True, timeout=8)
        if r.returncode != 0:
            return ("error", "")
        out = []
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.dumps(json.loads(line), sort_keys=True))
            except Exception:
                out.append(line)
        return ("ok", "\n".join(out))
    except Exception:
        return ("timeout", "")

TOOLS = {"jq": ["jq", "-c"], "gojq": ["gojq", "-c"], "jaq": ["jaq", "-c"]}
cases = parse_cases(os.path.join(HERE, "corpus", "s0-eval-core.test"))
splits = []
probes = 0
for i, c in enumerate(cases):
    rng = random.Random(10_000 + i)
    for k in range(3):
        inp = json.dumps(gen_value(rng))
        probes += 1
        res = {t: run(a, c["program"], inp) for t, a in TOOLS.items()}
        g = res["gojq"] != res["jq"]
        j = res["jaq"] != res["jq"]
        if g or j:
            splits.append({"i": i, "k": k, "program": c["program"][:100],
                           "input": inp[:100], "jq": res["jq"][0],
                           "gojq_splits": g, "jaq_splits": j})
json.dump(splits, open(os.path.join(HERE, "baseline", "oracle_splits.json"), "w"),
          indent=0)
print(f"probes: {probes} | human-split probes: {len(splits)}")
from collections import Counter
print("split by:", Counter(("gojq" if s["gojq_splits"] else "") +
                           ("+jaq" if s["jaq_splits"] else "")
                           for s in splits).most_common())
