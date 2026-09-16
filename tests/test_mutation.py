"""The fault injector must stay wide, and the score must stay readable.

A mutation score is a measurement of a test suite made through an instrument,
and the instrument has a width: the set of faults it can write. That width
does not appear in the number. The first injector swapped operators and
nothing else, and under it `examples/weak` scored 0.80 while differing from
its sibling implementation ONLY in two constants -- a fault the injector could
not express at all. The number was measuring the injector, and nothing in the
report said so.

So this file pins the instrument rather than any particular score:

  * every fault kind is reachable, so a kind cannot quietly stop firing;
  * docstrings are never mutated, since those are equivalent mutants by
    construction and would punish a documented program for being documented;
  * the sample is stratified, so a budget of twenty over a program that is
    90% string literals still reaches the constants;
  * and the property the whole exercise exists for, with its negative control:
    a suite fitted to one value per branch survives the boundary mutants, and
    a suite that probes the boundaries kills them. Both directions, because a
    low rate that came from a broken operator would look exactly the same.

    pytest tests/test_mutation.py          (or: python3 tests/test_mutation.py)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import kernel, pack

#: Every fault kind the injector claims to express must occur in this one file,
#: which is what makes the coverage assertion below meaningful.
IMPL = '''"""A banding function. This docstring must never be mutated."""


def label(value, offset):
    """Return the band for value, shifted by offset."""
    shifted = value + offset
    if shifted < 10:
        return "low"
    if shifted < 100 and offset >= 0:
        return "mid"
    return "high"


def describe(value, offset):
    return "band=" + label(value, offset)
'''

#: Written alongside the code, naming one comfortable value per branch and
#: never going near where a branch actually changes. It passes.
FITTED = '''import sys

sys.path.insert(0, ".")
from impl import describe, label

assert label(5, 0) == "low"
assert label(50, 0) == "mid"
assert label(500, 0) == "high"
assert describe(5, 0) == "band=low"
print("ok")
with open("OK", "w") as f:
    f.write("ok\\n")
'''

#: The same claim, judged by a suite that probes each boundary from both sides.
#: This is the negative control: without it, a low constant rate above could
#: just as well mean the constant operator was broken.
PROBING = FITTED.replace('assert label(5, 0) == "low"', '''assert label(5, 0) == "low"
assert label(9, 0) == "low"
assert label(10, 0) == "mid"
assert label(99, 0) == "mid"
assert label(100, 0) == "high"
assert label(0, -1) == "low"
assert label(50, -1) == "high"''')

KINDS = {"comparison", "arithmetic", "constant", "string",
         "boolean", "branch", "return", "argument"}


def _claim(work: str, name: str, check: str) -> str:
    """A sealed claim over IMPL, judged by `check`."""
    d = os.path.join(work, name)
    os.makedirs(d)
    with open(os.path.join(d, "impl.py"), "w") as f:
        f.write(IMPL)
    with open(os.path.join(d, "check.py"), "w") as f:
        f.write(check)
    subprocess.run("python3 check.py", shell=True, cwd=d, check=True,
                   capture_output=True)
    result = pack.pack(d, name, ["impl.py"], ["check.py"],
                       "python3 check.py", "OK")
    assert result["ok"], f"{name} seals"
    return d


def _survived(score: dict, needle: str) -> bool:
    return any(needle in identifier for identifier in score["survivors"])


def test_fault_injector_stays_wide() -> None:
    work = tempfile.mkdtemp(prefix="mutation-check-")
    try:
        # -- the instrument is as wide as it says it is ----------------------

        candidates = kernel._mutants("impl.py", IMPL)
        found = {c["kind"] for c in candidates}
        assert found == KINDS, \
            f"every fault kind must be reachable; missing {KINDS - found}, " \
            f"unexpected {found - KINDS}"

        # Docstrings are equivalent mutants: they survive everything, so
        # including them would make a documented program score worse.
        docstring_lines = {1, 5}
        assert not [c for c in candidates
                    if c["kind"] == "string" and c["line"] in docstring_lines], \
            "a docstring must never be a mutation site"

        # -- stratification: a small budget still reaches every kind ---------

        order = kernel._draw_order(candidates, "any-seed")
        assert len(order) == len(candidates), "the draw order loses nothing"
        assert len({m["kind"] for m in order[:len(KINDS)]}) == len(KINDS), \
            "the first draws must be one per kind, or a small sample of a " \
            "string-heavy program would never reach a constant"

        # -- THE PROPERTY, and its negative control --------------------------

        fitted = _claim(work, "fitted", FITTED)
        probing = _claim(work, "probing", PROBING)
        budget = len(candidates)
        weak = kernel.mutation_score(fitted, max_mutants=budget)
        strong = kernel.mutation_score(probing, max_mutants=budget)

        assert weak["mutants"] == strong["mutants"] > 0, \
            "both suites judge the same mutants, so the rates are comparable"
        assert strong["rate"] > weak["rate"], \
            f"probing the boundaries must detect more: {weak['rate']} " \
            f"vs {strong['rate']}"

        # The specific faults that motivated widening the injector: a threshold
        # off by one. Invisible to an operator swap, and the only difference
        # between the two implementations in examples/weak.
        for boundary in ("constant:10->10+1", "constant:10->10-1",
                         "constant:100->100+1", "constant:100->100-1"):
            assert _survived(weak, boundary), \
                f"a suite fitted to one value per branch must miss {boundary}"
            assert not _survived(strong, boundary), \
                f"and a suite that probes the boundary must catch {boundary}"

        # -- the report carries the fault model, since the rate cannot --------

        for score in (weak, strong):
            assert set(score["by_kind"]) <= KINDS and score["by_kind"], \
                "the kill rate is broken down by kind"
            assert sum(t["mutants"] for t in score["by_kind"].values()) \
                == score["mutants"], "and the breakdown accounts for the sample"
            assert score["pool_by_kind"], "the pool is reported per kind too"
            assert "unparseable" in score, \
                "mutants dropped for not compiling are counted, not silent"

        assert weak["by_kind"]["constant"]["rate"] \
            < weak["by_kind"]["branch"]["rate"], \
            "the breakdown must localise the blind spot the aggregate hides"

        # -- determinism: a score cannot be shopped for ----------------------

        again = kernel.mutation_score(fitted, max_mutants=budget)
        assert again["survivors"] == weak["survivors"], \
            "the sample is drawn from the root, so it is the same every time"
        assert kernel.verify(fitted)["ok"], "and measuring never moves a claim"

        print(f"mutation-ok (fitted {weak['rate']:.2f}, "
              f"probing {strong['rate']:.2f}, {budget} sites)")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    test_fault_injector_stays_wide()
