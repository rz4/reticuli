"""Which mutants the criteria already kill, and therefore which pressure is new.

A free click is only free if it buys something. Zeta's first ranked findings
were all the future-version clause -- every member refuses a document from the
future -- and the criteria already test exactly that. The agreement was real
and the finding was redundant, because `agreement` asks whether the members
behave alike and never asks whether a criterion already decides it. A queue
that cannot tell those apart spends signatures on pins that exist.

The test is mechanical and reuses the controls. A mutant is a change to the
implementation; the criteria are what decide membership. So:

  KILLED mutant    the gate refuses it. The behaviour it broke is already
                   pinned, and a pressure that only separates killed mutants
                   is redundant with criteria that exist.

  SURVIVING mutant the gate accepts it. The behaviour it broke is NOT pinned
                   -- the root admits an implementation that does this -- and
                   that is a hole in the criteria with a ready-made witness.
                   A pressure separating a survivor is a genuine free click.

This is ordinary mutation analysis pointed sideways. Mutation scoring asks
whether a suite is strong enough to keep. Here the same measurement says which
pressure is worth a signature, and every surviving mutant is itself the most
actionable finding zeta can produce: a named gap, a concrete witness, and no
member evicted by closing it.

Cost is real -- one full gate run per mutant -- so results are cached by the
digest of the mutant's bytes and the criteria that judged them.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

#: What the gate needs. Deliberately not the whole repository: the research
#: record and the paper are large and no criterion reads them.
CARRIED = ("criteria", "spec", "examples", "scripts", "gate.py",
           "reticuli.toml", "pyproject.toml")

GATE_TIMEOUT = 3600


def criteria_digest(repo):
    """What judged this. A kill result is only valid against fixed criteria."""
    sha = hashlib.sha256()
    for path in sorted((Path(repo) / "criteria").glob("*.py")):
        sha.update(path.name.encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def _stage(repo, mutant_tree, into):
    into.mkdir(parents=True)
    for name in CARRIED:
        source = Path(repo) / name
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, into / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, into / name)
    shutil.copytree(mutant_tree, into / "src",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return into


def judge(repo, control, workspace):
    """Run the criteria against one mutant. Killed means the gate refused it."""
    room = _stage(repo, Path(control["path"]), Path(workspace) / control["id"].replace(":", "-"))
    try:
        done = subprocess.run([sys.executable, "gate.py"], cwd=room, text=True,
                              capture_output=True, timeout=GATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"control": control["id"], "killed": True, "by": "timeout",
                "breaks": control.get("breaks")}
    failed = sorted({line.split()[-1] for line in done.stdout.splitlines()
                     if line.startswith("FAIL")})
    killed = done.returncode != 0
    expect = control.get("expect")
    return {"control": control["id"], "killed": killed,
            "by": failed or (None if not killed else "gate"),
            "breaks": control.get("breaks"), "target": control.get("target"),
            "expect": expect,
            # The instrument checking itself. A `killed` operator that lives
            # is a criterion gap; a `survives` operator that dies means a
            # criterion pinned something the specification left open, which
            # makes membership author-relative. Both are findings; neither is
            # allowed to pass unremarked.
            "contradicts_expectation": bool(
                expect in ("killed", "survives")
                and killed != (expect == "killed"))}


def report(repo, controls, workspace):
    """Kill or survival for every control, with the criteria that judged them.

    The baseline runs first and must pass. The room staged here is a subset of
    the repository, so a criterion that needed a file the subset omits would
    fail against every mutant alike -- and a false kill reads as "already
    pinned", which is the one wrong answer that silently empties the queue.
    If the unmutated tree cannot earn the gate in this room, no kill result
    from it means anything and the report refuses to be one.
    """
    baseline = judge(repo, {"id": "baseline", "path": str(Path(repo) / "src"),
                            "breaks": None}, workspace)
    if baseline["killed"]:
        raise ValueError(
            f"the unmutated tree does not earn the gate in the staged room "
            f"({baseline['by']}); kills measured here would be artefacts of "
            f"staging, not of mutation")
    rows = [judge(repo, control, workspace) for control in controls]
    return {"schema": "zeta.coverage.1",
            "criteria_digest": criteria_digest(repo),
            "baseline": baseline,
            "killed": sorted(r["control"] for r in rows if r["killed"]),
            "surviving": sorted(r["control"] for r in rows if not r["killed"]),
            "contradictions": sorted(r["control"] for r in rows
                                     if r["contradicts_expectation"]),
            "rows": rows}


def annotate(result, coverage):
    """Mark a split redundant when it only separates mutants already killed.

    Redundancy is a property of the pressure against the CURRENT criteria, so
    it carries the digest of those criteria: re-pin a criterion and the
    judgement has to be made again.
    """
    surviving = set(coverage["surviving"])
    separated = set(result.get("discriminates") or [])
    novel = sorted(separated & surviving)
    result = dict(result)
    result["coverage"] = {
        "criteria_digest": coverage["criteria_digest"],
        "separates_surviving": novel,
        # A pressure that separates nothing was never ranked, so it is neither
        # redundant nor novel -- it is simply unranked, and says so.
        "redundant": bool(separated) and not novel,
        "novel": bool(novel),
    }
    return result


def load(path):
    data = json.loads(Path(path).read_text())
    if data.get("schema") != "zeta.coverage.1":
        raise ValueError("unsupported coverage schema")
    return data
