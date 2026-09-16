"""Tests for `ret assess` — the thing that measures how much a claim proves.

Most of what this pins is REPORTING behaviour, which is unusual for a test
suite and is the point. A measurement tool that quietly reports "not measured"
as a number, or lets an unmeasurable dimension look like a measured zero, is
worse than one that refuses to answer: the reader has no way to tell the
difference. Each of the three states below therefore has a test, and the one
that already failed in practice has two.

    python3 tests/assess_check.py        (from the repository root)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from reticuli import assess, kernel

QUIRKCALC = os.path.join(ROOT, "examples", "quirkcalc")
WEAK = os.path.join(ROOT, "examples", "weak")
MAKE = os.path.join(ROOT, "examples", "make")


def _copy(src: str) -> str:
    """A scratch copy, so no test can disturb a sealed claim in the repository."""
    work = tempfile.mkdtemp(prefix="assess-check-")
    dst = os.path.join(work, os.path.basename(src))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def battery() -> None:
    scratch: list[str] = []
    try:
        # -- the three states are distinct, and each occurs for a real reason --

        claim = _copy(QUIRKCALC)
        scratch.append(os.path.dirname(claim))
        r = assess.assess(claim, mutants=4)
        assert "mutation" in r["measured"], "a mutable claim is measured"
        score = r["measured"]["mutation"]
        assert score["mutants"] == 4 and score["candidates"] > 4, \
            f"the sample and the pool are both reported: {score}"

        # MEASURED ZERO vs NOT MEASURED. Asking for no faults is not a finding
        # of zero adequacy, and printing 0.00 for it reads as "detects nothing".
        # This exact confusion shipped once; it does not get to ship twice.
        r0 = assess.assess(claim, mutants=0)
        assert "mutation" not in r0["measured"], \
            "an unsampled mutation run must not appear as a measurement"
        assert "mutation" in r0["not_measured"], "it is reported as not measured"
        assert "0" in r0["not_measured"]["mutation"], \
            "and it says how many were injected, so the reader can act on it"

        # NOT APPLICABLE: the injector reads source text, so a claim whose
        # generated output is a compiled binary cannot be scored at all. That
        # is different from scoring badly, and must not be reported as a rate.
        binary_claim = _copy(MAKE)
        scratch.append(os.path.dirname(binary_claim))
        subprocess.run(["make", "-s"], cwd=binary_claim, check=False,
                       capture_output=True)
        rb = assess.assess(binary_claim, mutants=4)
        if rb["gate"] == "earned":
            assert "mutation" in rb["not_applicable"], \
                f"a binary output is not applicable, not a zero: {rb}"
            assert "mutation" not in rb["measured"]

        # -- circularity: the property a model-written claim most needs stated --

        weak = _copy(WEAK)
        scratch.append(os.path.dirname(weak))
        rw = assess.assess(weak, mutants=0)
        circ = rw["measured"]["circularity"]
        assert circ["ok"] and circ["pinned_deciders"], \
            "a gate decided by a pinned file is not circular"

        # -- what is NOT measured is always stated, never omitted ------------

        for dimension in ("re_derivation", "independence", "generalization"):
            assert dimension in rw["not_measured"], \
                f"{dimension} must be reported as unmeasured, not left silent"

        # -- independence is a degree, and unknown when it cannot be known ---

        deg = assess.independence_degree
        assert deg(None, {"model": "x"})["degree"] == "unknown", \
            "without the original's producer there is nothing to compare"
        assert deg({"model": "a", "vendor": "v"}, {"model": "a", "vendor": "v"}
                   )["degree"] == "none", "the same model is not independence"
        assert deg({"model": "a", "vendor": "v"}, {"model": "b", "vendor": "v"}
                   )["degree"] == "same-vendor", "a sibling model is weak evidence"
        assert deg({"model": "a", "vendor": "v"}, {"model": "b", "vendor": "w"}
                   )["degree"] == "different-vendor", "a different vendor is stronger"
        assert "not established" in deg({"model": "a", "vendor": "v"},
                                        {"model": "b", "vendor": "w"})["why"], \
            "and it never claims to have PROVEN independence"

        # -- re-derivation: both outcomes, and a failure that stays ambiguous --

        producer = os.path.join(os.path.dirname(claim), "faithful.py")
        with open(producer, "w", encoding="utf-8") as f:
            f.write("import os, shutil\n"
                    f"shutil.copyfile({os.path.join(QUIRKCALC, 'calc.py')!r}, "
                    "os.environ['RETICULI_OUTPUT'])\n")
        ok = assess.assess(claim, mutants=0,
                           rebuild=f"{sys.executable} {producer}")
        red = ok["measured"]["re_derivation"]
        assert red["ok"] and red["root"] == ok["root"], \
            f"a faithful producer lands on the same root: {red}"

        broken = os.path.join(os.path.dirname(claim), "broken.py")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("raise SystemExit(3)\n")
        bad = assess.assess(claim, mutants=0, rebuild=f"{sys.executable} {broken}")
        red = bad["measured"]["re_derivation"]
        assert not red["ok"] and red["error"], "a failure is reported with its reason"
        assert len(red["causes"]) >= 4, \
            "a failed rebuild has several causes and the report lists them all"
        assert "producer" in red["causes"][0], \
            "a broken producer is listed first: likeliest, and cheapest to rule out"

        # -- assessing a claim never changes it ------------------------------

        before = kernel.read_manifest(claim)["root"]
        assess.assess(claim, mutants=2)
        assert kernel.read_manifest(claim)["root"] == before, \
            "measuring a claim must not move it"
        assert kernel.verify(claim)["ok"], "and it still verifies afterwards"

        print("assess-ok")
    finally:
        for path in scratch:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    battery()
