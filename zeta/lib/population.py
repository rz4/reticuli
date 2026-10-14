"""The standing population, keyed by the root each member earned against.

Membership is relative to a root. A trial that earned its verdict against a
criterion set that has since moved is a member of a RETIRED root: it is not
evicted retroactively, but it cannot be used to argue that a proposed
criterion preserves the current class, because it never faced the current
criteria. Only current-root members carry that argument.

The reticuli population is read from the closure harness: each trial claim
declares the root it had to earn in `trial.json`, and carries `TRIAL_OK` only
if it earned it. The authored implementation under `src/` is a member too --
it is one answer in the class, not the definition of the class -- and it is
probed alongside the reconstructions.
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "zeta.population.1"
TRIALS = Path("research/harness/closure/trialclaims")
LINEAGES = Path("research/harness/succession")


def _repo_root(repo):
    manifest = json.loads((Path(repo) / ".reticuli" / "manifest.json").read_text())
    root = manifest.get("root")
    if not isinstance(root, str) or len(root) != 64:
        raise ValueError("repository manifest carries no usable root")
    return root


def build(repo="."):
    """Read the closure harness into a population registry."""
    repo = Path(repo)
    current = _repo_root(repo)
    members, retired, refused = [], [], []
    for trial in sorted((repo / TRIALS).iterdir()):
        if not (trial / "trial.json").is_file():
            continue
        declared = json.loads((trial / "trial.json").read_text())
        run, family = declared["run"], declared["lineage"]
        earned = declared["expect_root"]
        tree = repo / LINEAGES / f"lineages-{run}" / family
        entry = {"id": trial.name, "run": run, "family": family,
                 "earned_root": earned,
                 "path": str(tree), "package": "tree"}
        if not (trial / "TRIAL_OK").exists():
            refused.append({**entry, "why": "no TRIAL_OK: the trial did not qualify"})
        elif earned != current:
            retired.append({**entry, "why": "earned against a root that has moved"})
        else:
            members.append(entry)
    members.append({"id": "shipped", "run": "shipped", "family": "authored",
                    "earned_root": current, "path": str(repo / "src"),
                    "package": "reticuli"})
    members.sort(key=lambda m: m["id"])
    return {"schema": SCHEMA, "name": "reticuli", "current_root": current,
            "members": members, "retired": retired, "refused": refused,
            "note": "members are members OF current_root; retired members must "
                    "be re-earned rather than inherited"}


def load(path):
    data = json.loads(Path(path).read_text())
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported population schema")
    if not data["members"]:
        raise ValueError("population has no current-root members")
    seen = {m["id"] for m in data["members"]}
    if len(seen) != len(data["members"]):
        raise ValueError("population repeats a member id")
    for member in data["members"]:
        if member["earned_root"] != data["current_root"]:
            raise ValueError(f"{member['id']} is not a member of current_root")
    return data
