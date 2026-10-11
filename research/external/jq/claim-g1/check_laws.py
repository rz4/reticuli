"""The law battery: intensional criteria a lookup table cannot satisfy.

S_0's observations are finite, so generation 1 memorized them (the
extensional collapse, generation-1.md). These laws quantify over inputs
GENERATED AT GATE TIME from fresh entropy — they do not exist until the
gate runs, so no table can carry them — and every expectation is either
computed by this checker from first principles or is a self-consistency
relation of the evaluator against itself. The reference implementations
are never consulted: the laws come from jq's documented algebra.

Generation stays inside the zones where that algebra is unambiguous:
integers within +/- 2^31 (no big-int precision divergence), short ASCII
strings (no unicode-collation edges), homogeneous arrays where order
matters. The seed is printed so any failure reproduces exactly.
"""
import json
import os
import random
import subprocess
import sys

SEED = int.from_bytes(os.urandom(8), "big")
rng = random.Random(SEED)
print(f"law seed: {SEED}")

N = 30  # cases per law


def ev(prog, value):
    """Run the produced evaluator; return ('ok', [parsed outputs]) or ('error',)."""
    r = subprocess.run([sys.executable, "jqeval.py", prog],
                       input=json.dumps(value), text=True,
                       capture_output=True, timeout=10)
    if r.returncode != 0:
        return ("error", None)
    out = []
    for line in r.stdout.splitlines():
        if line.strip():
            out.append(json.loads(line))
    return ("ok", out)


def gi():
    return rng.randint(-2**31, 2**31)


def gs():
    return "".join(rng.choice("abcdefgh XYZ_") for _ in range(rng.randint(0, 9)))


def gv(depth=0):
    r = rng.random()
    if depth > 2 or r < 0.35:
        return rng.choice([None, True, False, gi(), gs()])
    if r < 0.7:
        return [gv(depth + 1) for _ in range(rng.randint(0, 4))]
    return {gs() or "k": gv(depth + 1) for _ in range(rng.randint(0, 4))}


failures = []


def law(name, cases):
    bad = [c for c in cases if c is not None]
    if bad:
        failures.append(f"{name}: {len(bad)}/{len(cases)} e.g. {bad[0]!r:.140}")
    print(f"  {name:34} {'ok' if not bad else 'FAIL'}")


def expect(prog, value, want):
    got = ev(prog, value)
    if got != ("ok", want):
        return (prog, value, "got", got, "want", want)
    return None


# -- laws with checker-computed ground truth ---------------------------------
law("identity: . x == x", [expect(".", v, [v]) for v in (gv() for _ in range(N))])
law("index: .k on {k: x} == x",
    [expect(".k", {"k": v}, [v]) for v in (gv() for _ in range(N))])
law("length of array == element count",
    [expect("length", a, [len(a)])
     for a in ([gv() for _ in range(rng.randint(0, 6))] for _ in range(N))])
law("keys == sorted key list",
    [expect("keys", o, [sorted(o)])
     for o in ({gs() or str(i): gi() for i in range(rng.randint(0, 5))}
               for _ in range(N))])
law("integer addition",
    [expect(".a + .b", {"a": a, "b": b}, [a + b])
     for a, b in ((gi() // 2, gi() // 2) for _ in range(N))])
law("array concat length",
    [expect("(.a + .b) | length", {"a": a, "b": b}, [len(a) + len(b)])
     for a, b in (([gi() for _ in range(rng.randint(0, 4))],
                   [gs() for _ in range(rng.randint(0, 4))]) for _ in range(N))])
law("sort of integers == sorted",
    [expect("sort", a, [sorted(a)])
     for a in ([gi() for _ in range(rng.randint(0, 7))] for _ in range(N))])
law("reverse . reverse == identity",
    [expect("reverse | reverse", a, [a])
     for a in ([gv() for _ in range(rng.randint(0, 6))] for _ in range(N))])
law("map(.+1) on integers",
    [expect("map(. + 1)", a, [[x + 1 for x in a]])
     for a in ([gi() // 2 for _ in range(rng.randint(0, 6))] for _ in range(N))])
law(".[] enumerates in order",
    [None if ev(".[]", a) == ("ok", a) else ("enum", a, ev(".[]", a))
     for a in ([gv() for _ in range(rng.randint(0, 5))] for _ in range(N))])
law("tojson | fromjson == identity",
    [expect("tojson | fromjson", v, [v]) for v in (gv() for _ in range(N))])
law("has(k) is true on {k: x}",
    [expect('has("k")', {"k": v}, [True]) for v in (gv() for _ in range(N))])
law("indexing a number is an error",
    [None if ev(".a", n)[0] == "error" else ("no error", n)
     for n in (gi() for _ in range(N))])

# -- self-consistency laws (the evaluator against itself) --------------------
pool = [".", "sort", "reverse", "length", "keys", ". + 1", "map(. + 1)",
        "tojson", "add", "first", "last", "min", "max", "unique", "flatten"]
cases = []
for _ in range(N * 2):
    a, b = rng.choice(pool), rng.choice(pool)
    v = gv()
    lhs = ev(f"({a}) | ({b})", v)
    if lhs[0] == "error":
        continue  # composition may legitimately error; law applies to successes
    mid = ev(a, v)
    if mid[0] != "ok" or len(mid[1]) != 1:
        cases.append(("mid mismatch", a, b, v))
        continue
    rhs = ev(b, mid[1][0])
    if lhs != rhs:
        cases.append(("compose", a, b, v, lhs, rhs))
law("composition: (A|B) x == B(A x)", cases or [None])
law("sort idempotent",
    [None if ev("sort | sort", a) == ev("sort", a) else ("sort2", a)
     for a in ([gi() for _ in range(rng.randint(0, 7))] for _ in range(N))])

assert not failures, "laws broken (seed %d):\n  " % SEED + "\n  ".join(failures)
with open("LAWS_OK", "w") as f:
    f.write(f"seed {SEED}\n")
print("laws-ok")
