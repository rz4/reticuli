"""A queue entry must be a portable, tamper-evident witness.

Two failures this criterion exists to prevent, both of which happened while
the module was being written. First, a gate that reached back into the working
tree: it passed where it was minted and failed everywhere else, so an entry
only looked re-earnable. Second, a tamper test that "passed" because the gate
died on an import before it ever checked anything -- a green result from a
check that never ran.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import entry as entrylib, reduce as reducelib, split as splitlib

ROOT = "a" * 64
POPULATION = {"schema": "zeta.population.1", "name": "fixture",
              "current_root": ROOT,
              "members": [{"id": name, "earned_root": ROOT, "path": "/x",
                           "package": "p"} for name in ("one", "two")],
              "retired": [], "refused": []}
PRESSURE = {"schema": "zeta.pressure.1", "source": "fixture", "id": "f/case",
            "clause": "case", "simplicity": 0, "call": "f", "args": [1],
            "specified_reader_behaviour": "n/a", "origin": "fixture"}
OBSERVED = {"one": {"kind": "value", "value": {"plain": 1}},
            "two": {"kind": "refused", "error_type": "ClaimError",
                    "error_message": "no"}}


def check(condition, why):
    if not condition:
        raise SystemExit(f"entry_check: {why}")


def minted(into):
    result = reducelib.collapse(
        [splitlib.classify(POPULATION, PRESSURE, OBSERVED, {})])[0]
    path = entrylib.mint(into, POPULATION, result)
    check(path is not None, "a fresh pressure must mint an entry")
    return path


def gate(path):
    return subprocess.run([sys.executable, "check_split.py"], cwd=path,
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as directory:
    queue = Path(directory) / "queue"
    path = minted(queue)

    # The entry carries its own classifier. Without it the gate would only
    # replay at one fixed depth inside one working tree.
    for name in ("entry.json", "check_split.py", "reticuli.toml",
                 "_zeta/__init__.py", "_zeta/probe.py", "_zeta/split.py"):
        check((path / name).is_file(), f"an entry must carry {name}")

    document = entrylib.read(path)
    check(document["state"] == "undeclared",
          "a minted entry is undeclared; only a signature changes that")
    check(document["lane"] == "eviction", "a split entry takes the eviction lane")

    # The same pressure must not be able to occupy the queue twice.
    again = reducelib.collapse(
        [splitlib.classify(POPULATION, PRESSURE, OBSERVED, {})])[0]
    check(entrylib.mint(queue, POPULATION, again) is None,
          "a pressure already in the queue must not mint a second entry")

    # It replays where nothing of this repository sits above it.
    with tempfile.TemporaryDirectory() as elsewhere:
        away = Path(elsewhere) / "entry"
        shutil.copytree(path, away)
        done = gate(away)
        check(done.returncode == 0,
              f"an entry must replay away from its mint site: {done.stderr[-200:]}")
        check((away / "SPLIT_OK").read_text() == "ok\n",
              "a replayed entry writes its own gate output")

    # Every fabrication must be refused, and refused for the stated reason.
    tampers = [
        ("flipped observation", "did not re-earn",
         lambda d: d["split"]["observations"].__setitem__(
             "one", {"kind": "refused", "error_type": "ClaimError",
                     "error_message": "no"})),
        ("relabelled lane", "header disagrees",
         lambda d: d.__setitem__("lane", "contraction")),
        ("fabricated rank", "did not re-earn",
         lambda d: d["split"].__setitem__("rank", 7)),
        ("inflated breadth", "witness count",
         lambda d: d["split"].__setitem__("witness_count", 99)),
        ("disowned witness", "not among the witnesses",
         lambda d: d["split"].__setitem__("witnessed_by", ["f/other"])),
        ("reassigned class", "did not re-earn",
         lambda d: d["split"]["classes"].__setitem__(
             next(iter(d["split"]["classes"])), ["one", "two"])),
    ]
    for label, expected, mutate in tampers:
        with tempfile.TemporaryDirectory() as elsewhere:
            away = Path(elsewhere) / "entry"
            shutil.copytree(path, away)
            (away / "SPLIT_OK").unlink(missing_ok=True)
            document = json.loads((away / "entry.json").read_text())
            mutate(document)
            (away / "entry.json").write_text(json.dumps(document, indent=2,
                                                        sort_keys=True))
            done = gate(away)
            check(done.returncode != 0, f"{label} must be refused")
            check(expected in (done.stdout + done.stderr),
                  f"{label} must be refused for the right reason, not by "
                  f"accident: {(done.stdout + done.stderr)[-200:]}")
            check(not (away / "SPLIT_OK").exists(),
                  f"{label} must not leave a gate output behind")

print("entry-ok")
