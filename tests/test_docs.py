"""The prose that tells people how to run the checks must match what CI runs.

These commands drifted once: criteria/ gained a suite that only runs staged
(kernel_check.py), so the documented loop over criteria/*.py started failing
at the repository root, and CI had already moved to gate.py without the prose
following. Prose is not pinned -- editing it moves no root -- but it can be
tested, which is the next best thing.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_ci_runs_the_gate():
    assert "python3 gate.py" in _read(".github", "workflows", "ci.yml")


def test_docs_run_what_ci_runs():
    for doc in ("README.md", "CONTRIBUTING.md"):
        text = _read(doc)
        assert "python3 gate.py" in text, f"{doc} should run the gate, as CI does"
        assert "for f in criteria/*.py" not in text, (
            f"{doc} still documents the loop the gate replaced; "
            "kernel_check.py only runs staged, so the loop fails")


def test_contributing_names_the_claims_it_verifies():
    assert "examples/*" not in _read("CONTRIBUTING.md"), (
        "a glob over examples/ hits examples/self, which holds prose and no "
        "claim; name the claims, as ci.yml does")
