"""Honest-partial pack: feedback.warnings names the gaps a session trace
leaves — an observed write to a vanished file, an input inferred from command
text rather than an observed read, cost never established — instead of dropping
them silently. It is residue and advice; it never changes identity.

    pytest tests/test_honest_pack.py   (or: python3 tests/test_honest_pack.py)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reticuli import feedback


def _session(tmp: str, events: list[dict], files: dict[str, str]) -> None:
    os.makedirs(os.path.join(tmp, ".reticuli"))
    for name, body in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(body)
    with open(os.path.join(tmp, ".reticuli", "draft.jsonl"), "w",
              encoding="utf-8") as f:
        f.writelines(json.dumps(e) + "\n" for e in events)


def test_warnings_name_the_gaps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _session(
            tmp,
            events=[
                {"event": "write", "path": "solver.py", "via": "hook", "ts": 1.0},
                {"event": "write", "path": "gone.py", "via": "hook", "ts": 1.5},
                {"event": "bash", "cmd": "python3 check.py && printf ok > OK",
                 "via": "hook", "ts": 2.0},
            ],
            files={"solver.py": "def answer():\n    return 42\n",
                   "check.py": "import solver\nassert solver.answer() == 42\n"},
        )
        warns = feedback.warnings(tmp)
        kinds = {w["kind"] for w in warns}
        assert "observed-write-dropped" in kinds, \
            "a write to a now-gone file is named, not dropped silently"
        assert any("gone.py" in w["detail"] for w in warns), \
            "the dropped write names the file"
        assert "inferred-input" in kinds, \
            "an input taken from command text, not an observed read, is flagged"
        assert "cost-unestablished" in kinds, \
            "no transcript in the window means cost is unmeasured, and said so"
        assert all(set(w) == {"kind", "detail"} for w in warns), \
            "every finding is the two-field shape the CLI and --json rely on"


def test_observed_read_is_not_inferred() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _session(
            tmp,
            events=[
                {"event": "write", "path": "solver.py", "via": "hook", "ts": 1.0},
                {"event": "read", "path": "check.py", "via": "hook", "ts": 1.2},
                {"event": "bash", "cmd": "python3 check.py && printf ok > OK",
                 "via": "hook", "ts": 2.0},
            ],
            files={"solver.py": "def answer():\n    return 42\n",
                   "check.py": "import solver\nassert solver.answer() == 42\n"},
        )
        kinds = {w["kind"] for w in feedback.warnings(tmp)}
        assert "observed-write-dropped" not in kinds, "every write is present"
        assert "inferred-input" not in kinds, \
            "check.py was OBSERVED read, so it is not an inferred input"


if __name__ == "__main__":
    test_warnings_name_the_gaps()
    test_observed_read_is_not_inferred()
    print("honest-pack-ok")
