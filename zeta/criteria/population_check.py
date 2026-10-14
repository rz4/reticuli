"""Membership is relative to a root, and the registry must refuse to forget it.

The failure this criterion exists to prevent: a registry that lists every
trial that ever qualified, so a proposed criterion is judged to "preserve the
class" by members that never faced the current criteria. The repository's own
history supplies the case -- r19 earned its verdict, a later comment-only
change moved the root, and r19 was regrown as r21.
"""

import json
import sys
import tempfile
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import population as poplib

ROOT = "a" * 64
OTHER = "b" * 64


def registry(**overrides):
    base = {"schema": "zeta.population.1", "name": "fixture", "current_root": ROOT,
            "members": [{"id": "one", "earned_root": ROOT, "path": "/x", "package": "p"}],
            "retired": [], "refused": []}
    return {**base, **overrides}


def check(condition, why):
    if not condition:
        raise SystemExit(f"population_check: {why}")


def refuses(data, fragment):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "population.json"
        path.write_text(json.dumps(data))
        try:
            poplib.load(path)
        except ValueError as exc:
            check(fragment in str(exc),
                  f"expected a refusal mentioning {fragment!r}, got {exc}")
            return
    raise SystemExit(f"population_check: accepted a registry it must refuse "
                     f"({fragment})")


with tempfile.TemporaryDirectory() as directory:
    good = Path(directory) / "population.json"
    good.write_text(json.dumps(registry()))
    loaded = poplib.load(good)
    check(loaded["current_root"] == ROOT, "a well-formed registry must load")

# A member of another root is not a member of this one.
refuses(registry(members=[{"id": "one", "earned_root": OTHER, "path": "/x",
                           "package": "p"}]),
        "not a member of current_root")

# An empty population cannot support any argument about preserving the class.
refuses(registry(members=[]), "no current-root members")

# A repeated id would let one member be counted twice in a partition.
refuses(registry(members=[{"id": "one", "earned_root": ROOT, "path": "/x",
                           "package": "p"},
                          {"id": "one", "earned_root": ROOT, "path": "/y",
                           "package": "p"}]),
        "repeats a member id")

refuses(registry(schema="zeta.population.99"), "unsupported population schema")

# Against the repository itself: the split between current, retired and
# refused must be drawn by the recorded roots, not by hand.
repo = Path(__file__).resolve().parents[2]
if (repo / ".reticuli" / "manifest.json").exists():
    live = poplib.build(repo)
    current = live["current_root"]
    check(all(m["earned_root"] == current for m in live["members"]),
          "every member must have earned the current root")
    check(all(m["earned_root"] != current for m in live["retired"]),
          "a retired member earned a root that has moved")
    check(any(m["id"] == "shipped" for m in live["members"]),
          "the authored implementation is a member and must be probed")
    ids = [m["id"] for group in ("members", "retired", "refused")
           for m in live[group]]
    check(len(ids) == len(set(ids)), "no trial may appear in two groups")

print("population-ok")
