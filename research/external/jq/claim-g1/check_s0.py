"""The gate: every S_0 case re-earns against the produced evaluator.

The evaluator contract (the whole boundary): `python3 jqeval.py PROGRAM`
reads one JSON value from stdin and writes each output as compact JSON,
one per line, exit 0; on a program/runtime error, exit nonzero. Output
values are compared PARSED (key order and whitespace free), per line.
"""
import json, subprocess, sys

def cases(path):
    block = []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("#"):
            continue
        if not line.strip():
            if block:
                yield block[0], block[1], block[2:]
                block = []
            continue
        block.append(line)
    if len(block) >= 2:
        yield block[0], block[1], block[2:]

def norm(lines):
    out = []
    for ln in lines:
        try:
            out.append(json.dumps(json.loads(ln), sort_keys=True))
        except Exception:
            out.append(ln)
    return out

total = passed = 0
failures = []
for prog, inp, expect in cases("s0.test"):
    total += 1
    try:
        r = subprocess.run([sys.executable, "jqeval.py", prog], input=inp,
                           text=True, capture_output=True, timeout=10)
        got = [l for l in r.stdout.splitlines() if l.strip()]
        ok = r.returncode == 0 and norm(got) == norm(expect)
    except Exception:
        ok = False
    if ok:
        passed += 1
    elif len(failures) < 5:
        failures.append(prog[:80])
print(f"s0: {passed}/{total}")
assert passed == total, f"S_0 does not re-earn; first failures: {failures}"
with open("S0_OK", "w") as f:
    f.write(f"{passed}/{total}\n")
