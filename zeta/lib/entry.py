"""Mint a queue entry as its own claim, so it arrives already re-earned.

An entry is a directory holding the pressure, the split it induced, and a
recipe whose gate recomputes the split from the retained observations and
writes `SPLIT_OK`. A human reading the queue is therefore reading verified
witnesses: the classification is not a report about a run, it is a claim that
replays. The entry's name is the digest of its pressure, so the same pressure
lands in the same place and a queue cannot hold it twice.

An entry is UNDECLARED. It is not a criterion, it is not an obligation, and
nothing in the primary claim may read it -- a pending pressure that reached a
producer's room would be guidance rather than a criterion. The queue lives
outside every pinned input for that reason.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import probe

SCHEMA = "zeta.entry.1"

# The classifier travels with the entry. An entry whose gate reached back into
# the working tree would only replay where it was minted, at one fixed depth,
# which is not a portable witness -- and the reach was how the first version of
# this gate "passed" a tamper test it had actually failed to run.
CARRIED = ("kinds.py", "probe.py", "split.py")

GATE = '''import json, sys
sys.dont_write_bytecode = True
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
from _zeta import split as splitlib

entry = json.loads((here / "entry.json").read_text())
claimed = entry["split"]
recomputed = splitlib.classify(entry["population"], claimed["pressure"],
                               claimed["observations"], claimed.get("controls"))
# Everything classify decides must re-earn exactly. The two reduction fields
# are about which witnesses were collapsed onto this one, not about the
# classification, so they are checked for shape instead.
for key, value in recomputed.items():
    if claimed.get(key) != value:
        raise SystemExit(f"split did not re-earn: {key}")
if claimed["pressure"]["id"] not in claimed["witnessed_by"]:
    raise SystemExit("retained witness is not among the witnesses it stands for")
if claimed["witness_count"] != len(claimed["witnessed_by"]):
    raise SystemExit("witness count does not match the witness list")
if entry["lane"] != claimed["lane"] or entry["disposition"] != claimed["disposition"]:
    raise SystemExit("entry header disagrees with its own split")
if entry.get("kind") != claimed.get("kind"):
    raise SystemExit("entry header disagrees with its own rung")
Path("SPLIT_OK").write_text("ok\\n")
'''

INPUTS = ["check_split.py", "entry.json", "_zeta/__init__.py",
          "_zeta/kinds.py", "_zeta/probe.py", "_zeta/split.py"]

RECIPE = ('[claim]\nname = "zeta-queue-entry"\nformat = 4\ninputs = ' +
          json.dumps(sorted(INPUTS)) + '\n\n'
          '[[step]]\nkind = "gate"\noutput = "SPLIT_OK"\n'
          'class = "validated"\nrun = "python3 check_split.py"\n')


def mint(queue, population, result):
    """Write one entry. Returns its path, or None if it is already present."""
    name = probe.digest(result["pressure"])[:16]
    path = Path(queue) / name
    if path.exists():
        return None
    path.mkdir(parents=True)
    # The population travels with the entry, trimmed to what the split used:
    # a reader must be able to see which members were asked without resolving
    # paths that may have moved.
    carried = {"schema": population["schema"], "name": population["name"],
               "current_root": population["current_root"],
               "members": population["members"],
               "retired": population.get("retired", []),
               "refused": population.get("refused", [])}
    document = {"schema": SCHEMA, "id": name,
                "pressure_id": result["pressure"]["id"],
                "lane": result["lane"], "disposition": result["disposition"],
                "kind": result.get("kind"),
                "rank": result["rank"],
                "state": "undeclared",
                "population": carried, "split": result}
    (path / "entry.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    (path / "check_split.py").write_text(GATE)
    (path / "reticuli.toml").write_text(RECIPE)
    carried = path / "_zeta"
    carried.mkdir()
    (carried / "__init__.py").write_text(
        '"""The classifier that judged this entry, travelling with it."""\n')
    here = Path(__file__).resolve().parent
    for name in CARRIED:
        (carried / name).write_bytes((here / name).read_bytes())
    return path


def read(path):
    document = json.loads((Path(path) / "entry.json").read_text())
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported entry schema")
    return document


def survey(queue, current_root=None):
    """Read the queue, worst-first within each lane.

    A split is relative to a root. When the root moves, every entry observed
    against the old one stays a true record of what was seen then and stops
    being an argument about the class now -- the members it partitioned have
    become members of a retired root. Such an entry is marked STALE rather
    than deleted, and it sorts last, because a signature acting on it would be
    declaring a criterion on evidence from a class that no longer exists.
    """
    queue = Path(queue)
    if not queue.exists():
        return []
    entries = [read(p) for p in sorted(queue.iterdir()) if (p / "entry.json").is_file()]
    for document in entries:
        observed = document["split"]["current_root"]
        document["stale"] = bool(current_root) and observed != current_root
        document["observed_root"] = observed
    # Strength first, then cost. A fourth-kind finding is worth reading before
    # a first-kind one whatever lane either sits in, because the lane says what
    # signing would cost and the rung says whether there is anything to sign.
    from . import kinds as kindslib
    order = {"eviction": 0, "repair": 1, "contraction": 2}
    entries.sort(key=lambda e: (e["stale"],
                                -kindslib.RUNG.get(e.get("kind"), 0),
                                order.get(e["lane"], 9),
                                -e["rank"], e["pressure_id"]))
    return entries
