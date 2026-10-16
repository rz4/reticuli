# `zeta/agents/reconcile.py`

**What the root watcher knows and does, as plain functions.**

A root move obligates bookkeeping that has so far been done by hand after
every signature: rebuild the population registries, notice which queue
entries went stale, re-run the coverage battery against the changed
criteria, and confirm the promotion ledger still chains. Each was forgotten
at least once -- the ledger's own chain check caught an unrecorded promotion
on 2026-10-15 -- which is the argument for a watcher.

The split between observing and acting is the trust boundary. `observe`
reads everything and writes nothing. `act` rewrites only derived files
(registries, the coverage report); both of those are recomputable from the
repository, so the watcher can be wrong without costing evidence. What it
may NOT do is decide: an unrecorded promotion or a broken chain is reported
as a drift and left standing, because writing the promotion record is part
of promoting, and promoting is the keyholder's.

```python
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ZETA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ZETA))

from lib import coverage as coveragelib
from lib import entry as entrylib
from lib import ledger as ledgerlib
from lib import mutants as mutantlib
from lib import population as poplib

REGISTRIES = ZETA / "population"
QUEUE = ZETA / "queue"
LEDGER = ZETA / "promoted" / "ledger.jsonl"
COVERAGE = ZETA / "coverage" / "reticuli.json"
OBSERVATIONS = ZETA / "agents" / "observations.jsonl"
```

The registries the watcher keeps current. Only the reticuli population is
keyed by the moving root; deployment and jq are rebuilt alongside it
because their member lists drift for their own reasons (an interpreter
appears, a binary goes missing) and the rebuild is cheap either way.

```python
BUILDERS = {"reticuli": poplib.build,
            "deployment": poplib.deployment,
            "jq": poplib.jq}


def _repo_root(repo):
    manifest = json.loads(
        (Path(repo) / ".reticuli" / "manifest.json").read_text())
    return manifest["root"]


def observe(repo="."):
    """Read every surface the watcher answers for. Writes nothing."""
    repo = Path(repo)
    root = _repo_root(repo)
    out = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "repo_root": root,
           "registries": {}, "queues": {}, "ledger": {}, "coverage": {}}

    recorded_roots = {}
    for name in sorted(BUILDERS):
        path = REGISTRIES / f"{name}.json"
        if not path.is_file():
            out["registries"][name] = {"state": "absent"}
            continue
        recorded = json.loads(path.read_text()).get("current_root")
        recorded_roots[name] = recorded
```

A foreign population (jq) is deliberately NOT keyed by the
repository root: nobody sealed its members, so its registry
records a named sentinel instead. Reading that as "behind" would
have the watcher rebuilding it every cycle forever.

```python
        foreign = not (isinstance(recorded, str) and len(recorded) == 64
                       and all(c in "0123456789abcdef" for c in recorded))
        out["registries"][name] = {
            "state": "foreign" if foreign else
                     ("current" if recorded == root else "behind"),
            "recorded_root": recorded}

    for name in sorted(BUILDERS):
        queue = QUEUE / name
        if not queue.is_dir():
            continue
```

staleness is relative to the root the POPULATION answers to, which
for a foreign population is its sentinel, never the repo root

```python
        rows = entrylib.survey(queue, recorded_roots.get(name, root))
        out["queues"][name] = {"entries": len(rows),
                               "stale": sum(1 for r in rows if r["stale"])}

    try:
        records = ledgerlib.chain(LEDGER)
        tip = records[-1]["root_after"] if records else None
        out["ledger"] = {"chain": "unbroken", "tip": tip,
                         "records": len(records)}
    except ValueError as exc:
        out["ledger"] = {"chain": "BROKEN", "why": str(exc)}

    live = coveragelib.criteria_digest(repo)
    stored = None
    if COVERAGE.is_file():
        stored = json.loads(COVERAGE.read_text()).get("criteria_digest")
    out["coverage"] = {"state": "current" if stored == live else
                       ("absent" if stored is None else "stale"),
                       "criteria_digest": live, "measured_against": stored}
    return out


def drifts(observation):
    """Name every way the observation disagrees with itself.

    Two classes come out of this. A drift whose `fix` names an `act` step is
    mechanical and the watcher will close it. A drift with `fix: "keyholder"`
    is one the watcher must never close: deciding it is the signature's job,
    and a watcher that quietly repaired it would be an agent promoting.
    """
    root = observation["repo_root"]
    found = []
    for name, reg in observation["registries"].items():
        if reg["state"] in ("behind", "absent"):
            found.append({"kind": f"registry-{reg['state']}", "which": name,
                          "fix": "rebuild-registries"})
    ledger = observation["ledger"]
    if ledger.get("chain") == "BROKEN":
        found.append({"kind": "broken-chain", "why": ledger["why"],
                      "fix": "keyholder"})
    elif ledger.get("tip") and ledger["tip"] != root:
        found.append({
            "kind": "unrecorded-promotion",
            "why": f"the ledger's last promotion ends at "
                   f"{ledger['tip'][:12]} but the repository is at "
                   f"{root[:12]}; recording the move is part of making it",
            "fix": "keyholder"})
    if observation["coverage"]["state"] != "current":
        found.append({"kind": f"coverage-{observation['coverage']['state']}",
                      "fix": "run-battery"})
    for name, q in observation["queues"].items():
        if q["stale"]:
```

informational: stale entries are correct records of a retired
class, already sorted last by survey; nothing rewrites them

```python
            found.append({"kind": "stale-entries", "which": name,
                          "count": q["stale"], "fix": "none"})
    return found


def act(repo, found, battery=True):
    """Close every mechanical drift. Derived files only.

    The battery is the expensive step -- one full gate run per mutant -- so
    it can be declined (`battery=False`), in which case the coverage drift
    stays on the report instead of being silently dropped.
    """
    actions = []
    if any(d["fix"] == "rebuild-registries" for d in found):
        REGISTRIES.mkdir(parents=True, exist_ok=True)
        for name, builder in sorted(BUILDERS.items()):
            try:
                data = builder(repo)
            except Exception as exc:                    # a missing binary or
                actions.append({"did": "rebuild-failed", "which": name,
                                "why": str(exc)[:200]})  # interpreter is a
                continue                                 # finding, not a crash
            (REGISTRIES / f"{name}.json").write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n")
            actions.append({"did": "rebuilt-registry", "which": name,
                            "members": len(data.get("members", []))})
    if battery and any(d["fix"] == "run-battery" for d in found):
        with tempfile.TemporaryDirectory() as trees, \
                tempfile.TemporaryDirectory() as rooms:
            built, missed = mutantlib.build(repo, trees)
            report = coveragelib.report(repo, built, rooms)
        COVERAGE.parent.mkdir(parents=True, exist_ok=True)
        COVERAGE.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        actions.append({"did": "ran-battery", "mutants": len(built),
                        "not_built": len(missed),
                        "killed": len(report["killed"]),
                        "surviving": report["surviving"]})
    return actions


def cycle(repo=".", battery=True):
    """One watch cycle: observe, close what is mechanical, observe again.

    The second observation is the point: the report carries what remains
    AFTER acting, so a drift still present at the end is either declined
    work (the battery) or the keyholder's -- never something the watcher
    believes it fixed. Appends to the observation log only when there was
    something to say; a quiet repository leaves no residue.
    """
    before = observe(repo)
    found = drifts(before)
    actions = act(repo, found, battery=battery)
    after = drifts(observe(repo)) if actions else found
    report = {"when": before["when"], "repo_root": before["repo_root"],
              "drifts": found, "actions": actions, "remaining": after}
    if found or actions:
        OBSERVATIONS.parent.mkdir(parents=True, exist_ok=True)
        with open(OBSERVATIONS, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, sort_keys=True) + "\n")
    return report
```

---
*Generated from `zeta/agents/reconcile.py` by `docs/weave.py`. The implementation is a reproducible artifact — one member of the equivalence class its acceptance criteria define — and this page is regenerated with it. Edits belong in the source.*
