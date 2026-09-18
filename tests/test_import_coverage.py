"""Coverage sees the canonical Python shape, and executed scripts are
deciders.

`python3 check.py && printf ok > PASSED` never names the implementation;
check.py reaches it with `from primes import is_prime`. The advisor must
cover primes.py through that one level of import, and must not misread
check.py — a file the command EXECUTES — as the gate's output. Found live,
by the first user to run the tutorial against a real Python project.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import feedback


def _session(tmp_path, check_body):
    (tmp_path / ".reticuli").mkdir()
    (tmp_path / "primes.py").write_text("def is_prime(n):\n    return n == 2\n")
    (tmp_path / "check.py").write_text(check_body)
    (tmp_path / "PASSED").write_text("ok")
    gate = "python3 check.py && printf ok > PASSED"
    events = [{"event": "write", "path": "primes.py", "ts": 1.0},
              {"event": "write", "path": "check.py", "ts": 2.0},
              {"event": "bash", "cmd": gate, "ts": 3.0}]
    (tmp_path / ".reticuli" / "draft.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n")
    return str(tmp_path)


def _row(report, path):
    return next(f for f in report["files"] if f["path"] == path)


def test_import_covers_the_implementation(tmp_path):
    r = feedback.advise(_session(tmp_path,
                                 "from primes import is_prime\nassert is_prime(2)\n"))
    assert _row(r, "primes.py")["covered"], \
        "the check imports it: the canonical flow needs no workaround"
    assert _row(r, "primes.py")["declared"] == "generated"
    assert not r["uncovered"] and r["sealable"]


def test_executed_check_is_a_decider_not_an_output(tmp_path):
    r = feedback.advise(_session(tmp_path,
                                 "from primes import is_prime\nassert is_prime(2)\n"))
    row = _row(r, "check.py")
    assert row["declared"] == "generated" and row["kind"] == "produced", \
        "a script the command runs is not the gate's verdict"
    assert _row(r, "PASSED")["declared"] == "validated", \
        "the redirect target is the verdict"


def test_an_unrelated_implementation_stays_uncovered(tmp_path):
    r = feedback.advise(_session(tmp_path, "assert 2 + 2 == 4\n"))
    assert not _row(r, "primes.py")["covered"], \
        "a check that never mentions the module does not cover it"
    assert r["uncovered"] == ["primes.py"]
