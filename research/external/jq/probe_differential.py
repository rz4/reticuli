"""Differential probes: seeded-random inputs per S_0 program, run through
the SAMPLE, reference jq, gojq, and jaq. Divergences of the sample from
reference = M candidates; human splits on the same probe = corroboration
(or, where humans split and the corpus never looked, H-shadow / novelty
leads). Deterministic by seed; the probes are not in any training set."""
import json
import os
import random
import subprocess
import sys

SAMPLE = sys.argv[1]
K = int(sys.argv[2]) if len(sys.argv) > 2 else 3
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "baseline"))
from run_baseline import parse_cases


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


TOOLS = {"sample": [sys.executable, os.path.join(SAMPLE, "jqeval.py")],
         "jq": ["jq", "-c"], "gojq": ["gojq", "-c"], "jaq": ["jaq", "-c"]}
cases = parse_cases(os.path.join(HERE, "corpus", "s0-eval-core.test"))
M, human_split_hits, agree, probes = [], 0, 0, 0
for i, c in enumerate(cases):
    rng = random.Random(10_000 + i)
    for _ in range(K):
        inp = json.dumps(gen_value(rng))
        probes += 1
        res = {t: run(a, c["program"], inp) for t, a in TOOLS.items()}
        if res["sample"] == res["jq"]:
            agree += 1
            continue
        if res["gojq"] != res["jq"] or res["jaq"] != res["jq"]:
            human_split_hits += 1
        M.append({"i": i, "program": c["program"][:100], "input": inp[:100],
                  "sample": res["sample"][0], "jq": res["jq"][0],
                  "gojq_splits": res["gojq"] != res["jq"],
                  "jaq_splits": res["jaq"] != res["jq"]})
OUTNAME = sys.argv[3] if len(sys.argv) > 3 else "probes_out.json"
json.dump(M, open(os.path.join(HERE, "baseline", OUTNAME), "w"),
          indent=0)
print(f"probes: {probes} | sample agrees with jq: {agree} | M candidates: {len(M)}")
print(f"of M, probes where a HUMAN implementation also splits from jq: {human_split_hits}")
from collections import Counter
print("M by (sample-status, jq-status):",
      Counter((m["sample"], m["jq"]) for m in M).most_common(6))
