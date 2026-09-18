"""`ret run` captures a command's file effects: a before/after content scan
turns created and modified files into write events, so work a script or
subprocess does enters the trace even when no editor hook saw it. A pure read
changes no content, so it is not claimed as a write, and `run` stays silent.

    pytest tests/test_run_capture.py   (or: python3 tests/test_run_capture.py)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import authoring, cli


def _trace(ws: str) -> list[dict]:
    with open(os.path.join(ws, authoring.TRACE), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _ws(tmp: str) -> str:
    os.makedirs(os.path.join(tmp, ".reticuli"))
    with open(os.path.join(tmp, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("one\n")
    return tmp


def test_run_captures_created_and_modified() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(tmp)
        rc = cli.run("printf two > seed.txt; printf hi > made.txt", ws)
        assert rc == 0
        ev = _trace(ws)
        writes = {e["path"] for e in ev if e.get("event") == "write"}
        assert "made.txt" in writes, "a file the command created is captured"
        assert "seed.txt" in writes, "a file the command modified is captured"
        bash = [e for e in ev if e.get("event") == "bash"]
        assert bash and bash[0]["via"] == "shell" and bash[0]["rc"] == 0, \
            "the command is recorded with its exit code"


def test_run_does_not_claim_pure_reads() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(tmp)
        cli.run("cat seed.txt > /dev/null", ws)
        ev = _trace(ws)
        writes = {e["path"] for e in ev if e.get("event") == "write"}
        assert writes == set(), \
            "reading a file changes no content, so no write is invented"


def test_run_records_a_nonzero_exit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = _ws(tmp)
        rc = cli.run("exit 3", ws)
        assert rc == 3, "the child's exit status is returned"
        bash = [e for e in _trace(ws) if e.get("event") == "bash"]
        assert bash and bash[0]["rc"] == 3, "and recorded honestly in the trace"


if __name__ == "__main__":
    test_run_captures_created_and_modified()
    test_run_does_not_claim_pure_reads()
    test_run_records_a_nonzero_exit()
    print("run-capture-ok")
