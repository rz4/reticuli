"""The claim over calc.py: every case present must hold.

A case file is two lines: the expression, then the expected value — an
integer, or the literal string CalcError. The gate judges whatever cases are
in the room, so a resealed record with a kept fraction judges just the kept
fraction (scripts/heldout.py relies on exactly this).
"""
import glob
import sys

sys.path.insert(0, ".")
from calc import CalcError, evaluate

cases = sorted(glob.glob("cases/*.txt"))
assert cases, "no cases in the room"
for path in cases:
    with open(path, encoding="utf-8") as f:
        expr, want = f.read().splitlines()[:2]
    if want == "CalcError":
        try:
            got = evaluate(expr)
        except CalcError:
            continue
        raise AssertionError(f"{path}: {expr!r} = {got}, expected CalcError")
    got = evaluate(expr)
    assert got == int(want), f"{path}: {expr!r} = {got}, expected {want}"
print(f"quirkcalc-ok ({len(cases)} cases)")
