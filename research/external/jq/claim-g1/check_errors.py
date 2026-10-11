"""Error-condition laws: the language's refusals are specification.

Generation 2 measured every sample, both families, more PERMISSIVE than
jq somewhere: succeeding where the language errors. S_0 could not catch
it — a corpus contains only the error cases somebody wrote down.

These laws are INTENSIONAL like the value laws: for each typed builtin,
wrong-typed inputs are GENERATED at gate time from fresh entropy and
the evaluator must RAISE on every one. (Generation 1's lesson: a fixed
list of 36 error pairs would just be a smaller table to memorize.)

Every condition here was confirmed UNANIMOUS across reference jq, gojq,
and jaq before being written (the measure-before-pin rule) — so the
laws encode the language, not one implementation's taste. Conditions
where the three disagree are deliberately EXCLUDED and recorded as
ambiguity-zone items instead: join on objects and nested arrays,
getpath on malformed paths, flatten on non-arrays, contains with
mismatched operands, implode with out-of-range codepoints, and
range("a") — which HANGS jaq (a liveness divergence this battery found).
"""
import json
import os
import random
import subprocess
import sys

SEED = int.from_bytes(os.urandom(8), "big")
rng = random.Random(SEED)
print(f"error-law seed: {SEED}")
N = 8  # generated wrong-typed inputs per law


def ev_raises(prog, value):
    """True iff the evaluator refuses (nonzero exit) on this input."""
    r = subprocess.run([sys.executable, "jqeval.py", prog],
                       input=json.dumps(value), text=True,
                       capture_output=True, timeout=10)
    return r.returncode != 0


def numbers():
    return rng.choice([0, 1, -1, 7, 255, -2**20, rng.randint(-10**6, 10**6),
                       round(rng.uniform(-1e3, 1e3), 3)])


def strings():
    return "".join(rng.choice("abcXYZ 019_") for _ in range(rng.randint(0, 8)))


def booleans():
    return rng.choice([True, False])


def arrays():
    return [rng.choice([numbers(), strings(), booleans(), None])
            for _ in range(rng.randint(0, 4))]


def objects():
    return {strings() or "k": rng.choice([numbers(), strings(), None])
            for _ in range(rng.randint(0, 3))}


def nonempty_objects():
    """reverse/transpose/min are defined via length, so EMPTY containers
    pass vacuously (jq: reverse on {} is []). The law is about non-empty."""
    return {strings() or f"k{i}": numbers() for i in range(rng.randint(1, 3))}


def nonzero_numbers():
    """Same vacuity: jq's reverse on 0 yields [] (length 0, nothing
    indexed) while 5 errors. NOTE: on 0, gojq and jaq BOTH error — an
    undocumented three-way split this battery found; it is therefore an
    ambiguity-zone item and excluded from the law."""
    n = 0
    while n == 0:
        n = rng.choice([numbers(), rng.randint(1, 10**6), -rng.randint(1, 10**6)])
    return n


# (program, generators of inputs the language REFUSES) — each unanimous
# across jq, gojq and jaq, verified before landing.
LAWS = [
    ("to_entries", [numbers, strings, booleans]),
    # transpose is DROPPED, deliberately: its refusal depends on the max
    # length of the VALUES ({"k": 0} is vacuous, {"a": 1} errors), so it
    # is not a type-level law. Recorded as a complexity item instead.
    ("implode", [strings, numbers, objects]),
    ("explode", [numbers, objects, booleans]),
    ('delpaths("x")', [arrays]),
    ("setpath([[1]]; 1)", [lambda: None, objects]),
    ("path(1)", [lambda: None, numbers]),
    ('path("a")', [lambda: None, objects]),
    ("keys", [numbers, strings, booleans]),
    ("length", [booleans]),
    ("add", [numbers, booleans]),
    ("sort", [numbers, nonempty_objects, strings]),
    ("unique", [strings, numbers, nonempty_objects]),
    ("reverse", [nonzero_numbers, nonempty_objects, booleans]),
    ("min", [nonempty_objects, numbers]),
    ("any", [numbers, strings]),   # objects are LEGAL: any iterates values
    ("tonumber", [objects, arrays, booleans]),
    ("ascii_downcase", [numbers, arrays, objects]),
    ('has("a")', [numbers, strings, booleans]),
    ("in(5)", [strings, objects]),
    ('splits(",")', [numbers, arrays, objects]),
    ("indices([1,2])", [strings]),
    ("index(1)", [strings]),
    ("ltrimstr(1)", [strings]),
    (". - 1", [objects, strings, arrays]),
    ('. - "a"', [strings, numbers]),
    ('. + "a"', [numbers, booleans, objects]),
    (". * 2", [arrays, booleans]),
    (". / 2", [objects, booleans, arrays]),
]

failures = []
for prog, gens in LAWS:
    bad = []
    for _ in range(N):
        value = rng.choice(gens)()
        if not ev_raises(prog, value):
            bad.append(value)
    status = "ok" if not bad else f"FAIL (accepted {bad[:2]!r})"
    print(f"  refuses {prog:24} {status}")
    if bad:
        failures.append(f"{prog} accepted {bad[:3]!r}")

# A refusal law must not be satisfied by refusing EVERYTHING: the value
# laws (check_laws.py) already pin the success side, and this guard keeps
# the two batteries from being gamed in opposite directions.
sanity = [("length", [1, 2, 3]), ("keys", {"a": 1}), ("add", [1, 2]),
          ("to_entries", {"a": 1}), ("sort", [3, 1]), (". + 1", 41)]
for prog, value in sanity:
    if ev_raises(prog, value):
        failures.append(f"{prog} wrongly refuses the valid input {value!r}")
print(f"  sanity (valid inputs still accepted)  "
      f"{'ok' if not any('wrongly' in f for f in failures) else 'FAIL'}")

assert not failures, ("error laws broken (seed %d):\n  " % SEED) + "\n  ".join(failures)
with open("ERRORS_OK", "w") as f:
    f.write(f"seed {SEED}\n")
print("error-laws-ok")
