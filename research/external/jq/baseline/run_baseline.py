"""The feral-population baseline: every case in the frozen jq corpus run
against jq, gojq, and jaq; per-case verdicts and the disagreement map.
Research tooling — the oracles stay OUTSIDE S (design commitment 4)."""
import json, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "corpus", "jq-1.8.1.test")
TOOLS = {"jq": ["jq", "-c"], "gojq": ["gojq", "-c"], "jaq": ["jaq", "-c"]}

def parse_cases(path):
    cases, block = [], []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#") or (not line.strip() and not block):
            if not line.strip() and block:
                pass
            continue
        if not line.strip():
            if block:
                cases.append({"program": block[0], "input": block[1],
                              "expect": block[2:]})
                block = []
            continue
        block.append(line)
    if len(block) >= 2:
        cases.append({"program": block[0], "input": block[1], "expect": block[2:]})
    return cases

def run(tool_argv, program, inp):
    try:
        r = subprocess.run(tool_argv + [program], input=inp, text=True,
                           capture_output=True, timeout=10)
        out = [l for l in r.stdout.splitlines() if l.strip()]
        return {"rc": r.returncode, "out": out}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "out": ["<TIMEOUT>"]}
    except Exception as e:
        return {"rc": -2, "out": [f"<ERR {type(e).__name__}>"]}

def norm(lines):
    o = []
    for l in lines:
        try: o.append(json.dumps(json.loads(l), sort_keys=True))
        except Exception: o.append(l)
    return o

cases = parse_cases(CORPUS)
print(f"{len(cases)} cases parsed", file=sys.stderr)
rows = []
for i, c in enumerate(cases):
    res = {t: run(argv, c["program"], c["input"]) for t, argv in TOOLS.items()}
    expect = norm(c["expect"])
    row = {"i": i, "program": c["program"][:120]}
    for t in TOOLS:
        ok = res[t]["rc"] == 0 and norm(res[t]["out"]) == expect
        row[t] = "pass" if ok else ("error" if res[t]["rc"] != 0 else "diff")
    rows.append(row)
    if i % 200 == 0:
        print(f"  {i}...", file=sys.stderr)
json.dump(rows, open(os.path.join(HERE, "baseline.json"), "w"), indent=0)
from collections import Counter
combo = Counter(tuple(r[t] for t in TOOLS) for r in rows)
print("\n(jq, gojq, jaq) verdict combinations:")
for k, v in combo.most_common():
    print(f"  {k}: {v}")
per = {t: sum(1 for r in rows if r[t] == "pass") for t in TOOLS}
print("per-tool corpus pass:", per, "of", len(rows))
dis = [r for r in rows if len({r[t] for t in TOOLS}) > 1]
print("cases where the three DISAGREE:", len(dis))
