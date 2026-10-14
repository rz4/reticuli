"""Deliberately broken members, used as controls so the ranker can rank.

The first sweep's controls were the trials that failed to qualify, and they
discriminated nothing: those trials failed for reasons elsewhere, so on the
record surface they behaved exactly like members. A ranker that cannot
separate any two pressures ranks nothing, and every free click looked equally
worth a signature.

A mutant fixes that without waiting for a population. It is the authored tree
with one targeted edit -- a comparison flipped, a guard deleted, a refusal
turned into a pass -- and it is NEVER a member: nobody sealed it and it would
not earn the root. It sits in the control set, where its only job is to answer
a pressure differently from the members. A pressure that no mutant can tell
apart from a conforming member is a pressure that would not have caught a
broken implementation, whatever else it is.

This is the same instrument the kernel already uses for mutation scoring,
turned around: there, mutants measure whether a suite is strong enough; here,
they measure whether a probe is sharp enough.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

#: Each operator is (name, pattern, replacement, what breaking it should cost).
#: They target refusal paths on purpose, because that is where the project's
#: own history says implementations drift: a guard that was never tested is a
#: guard some conforming-looking member will not have.
OPERATORS = [
    # Anchored on the line that follows, because `record_validate(doc)` is
    # called from the reader too and an operator that matches twice would
    # break two things at once -- or, as it did first, be dropped silently.
    ("skip-validation",
     r"^(\s*)record_validate\(doc\)\n(\s*)return json\.dumps",
     r"\1pass  # mutant\n\2return json.dumps",
     "a canonicalizer that validates nothing"),
    ("accept-any-version",
     r"^(\s*)if version > RECORD_FORMAT:$", r"\1if False:  # mutant",
     "a reader that accepts a document from the future"),
    ("ignore-unknown-members",
     r"^(\s*)unknown = set\(doc\) - members$", r"\1unknown = set()  # mutant",
     "a reader that lets an unnamed member through"),
    ("refuse-nothing",
     r'^(\s*)raise ClaimError\(f"not a record: \{reason\}"\)$',
     r"\1return  # mutant",
     "a validator whose refusal does not refuse"),
]

TARGET = Path("reticuli") / "_kernel" / "attest.py"


def build(repo, into, operators=None):
    """Copy the authored tree once per operator and apply that one edit.

    Returns control members, ready to hand to a split as controls. An operator
    whose pattern does not match is reported rather than skipped silently: a
    mutant that was never built would otherwise look like a pressure nothing
    could discriminate.
    """
    source = Path(repo) / "src"
    into = Path(into)
    built, missed = [], []
    for name, pattern, replacement, why in (operators or OPERATORS):
        tree = into / name
        if tree.exists():
            shutil.rmtree(tree)
        shutil.copytree(source, tree, ignore=shutil.ignore_patterns("__pycache__"))
        path = tree / TARGET
        text = path.read_text()
        changed, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count != 1:
            missed.append({"operator": name, "matches": count,
                           "why": "pattern did not match exactly once"})
            shutil.rmtree(tree)
            continue
        path.write_text(changed)
        built.append({"id": f"mutant:{name}", "run": "mutant", "family": "broken",
                      "earned_root": None, "path": str(tree),
                      "package": "reticuli", "driver": "python-package",
                      "breaks": why})
    return built, missed


def session(repo):
    """A temporary directory of mutants, cleaned up afterwards."""
    return tempfile.TemporaryDirectory(prefix="zeta-mutants-")
