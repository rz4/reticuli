"""A cold-gate refusal is a signpost, not a stack dump.

When a file the gate imports was authored outside observation, it never enters
the claim and the cold re-earn fails on the import. Two guarantees protect the
newcomer who hits this: `feedback.advise` sees the hidden dependency BEFORE pack
(so `status` never falsely promises "packable"), and `authoring.build_claim`
reports the exception and the fix rather than a truncated traceback. Declaring
the file then seals.

    pytest tests/test_cold_gate_diagnostic.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import authoring, feedback, kernel

CHECK = "from solver import is_prime\nassert is_prime(7) and not is_prime(8)\n"
SOLVER = "def is_prime(n):\n    return n > 1 and all(n % d for d in range(2, n))\n"


def _session(tmp: str, events: list[dict], files: dict[str, str]) -> None:
    os.makedirs(os.path.join(tmp, ".reticuli"))
    for name, body in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(body)
    with open(os.path.join(tmp, ".reticuli", "draft.jsonl"), "w",
              encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in events)


def _events() -> list[dict]:
    # The gate ran (so OK is a validated verdict and check.py a named input),
    # but no write/read event ever touched solver.py: it is present on disk yet
    # unobserved, exactly the state a hand-authored file has with no live agent.
    return [{"event": "bash", "cmd": "python3 check.py && printf ok > OK",
             "via": "shell", "ts": 2.0}]


def test_hidden_dependency_is_seen_before_pack() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _session(tmp, _events(), {"check.py": CHECK, "solver.py": SOLVER, "OK": "ok"})
        report = feedback.advise(tmp)
        assert "solver.py" in report["hidden"], \
            "a file a gate imports but nothing observed is a hidden dependency"
        assert not report["sealable"], "so the session is not falsely 'packable'"
        assert "solver.py" in report["nudge"] and "--generated" in report["nudge"], \
            "and the nudge names the file and the flag that pins it"


def test_cold_gate_failure_names_the_file_and_the_fix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _session(tmp, _events(), {"check.py": CHECK, "solver.py": SOLVER, "OK": "ok"})
        into = os.path.join(tmp, "out.claim")
        try:
            authoring.build_claim(tmp, ["OK"], into)
        except kernel.ClaimError as e:
            msg = str(e)
        else:
            raise AssertionError("pack must refuse a claim that cannot rebuild")
        assert "No module named 'solver'" in msg, \
            "the refusal reports the exception, not the traceback header"
        assert "Traceback" not in msg, "and never the raw traceback"
        assert "solver.py" in msg and "--generated" in msg, \
            "the hint names the missing file and how to declare it"


def test_declaring_the_file_seals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _session(tmp, _events(), {"check.py": CHECK, "solver.py": SOLVER, "OK": "ok"})
        into = os.path.join(tmp, "out.claim")
        result = authoring.build_claim(tmp, ["OK"], into, generated=["solver.py"])
        assert result["root"], "declaring solver.py as generated lets it seal cold"
        assert "solver.py" in [s["output"] for s in result["steps"]
                               if s["kind"] == "produce"], \
            "and solver.py is a generated produce step in the recipe"


if __name__ == "__main__":
    test_hidden_dependency_is_seen_before_pack()
    test_cold_gate_failure_names_the_file_and_the_fix()
    test_declaring_the_file_seals()
    print("cold-gate-diagnostic-ok")
