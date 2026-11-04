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
    """The gate CI runs is the claim's own, and the badge reaches it.

    The suite moved into a reusable workflow on 2026-11-04 so that a starved
    macOS runner could stop deciding the README badge, which split this into
    two questions: does the suite still run `gate.py` rather than a
    reimplementation of it, and does the workflow the badge reports still
    reach that suite.  Asserting only the first would let ci.yml quietly stop
    calling it.
    """
    suite = _read(".github", "workflows", "suite.yml")
    assert "python3 gate.py" in suite, (
        "the suite must run the claim's own gate, not a loop over criteria/")

    ci = _read(".github", "workflows", "ci.yml")
    assert "./.github/workflows/suite.yml" in ci, (
        "ci.yml — the workflow the README badge reports — must call the "
        "suite, or the badge stops meaning the gate passed")


def test_the_macos_leg_still_runs_somewhere():
    """It does not gate, but it must not vanish.

    macOS is the only platform in CI with a functional seatbelt sandbox, and
    the suites take a different branch there; a gate piping into `diff -u`
    once passed on Linux and died under seatbelt.  Taking the leg off the
    badge is deliberate.  Losing it is not.
    """
    macos = _read(".github", "workflows", "macos.yml")
    assert "macos-latest" in macos
    assert "./.github/workflows/suite.yml" in macos, (
        "macos.yml must call the same suite, or the platform that reports "
        "and the platform that gates can drift apart")


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
        "claim; name the claims, as the suite workflow does")
