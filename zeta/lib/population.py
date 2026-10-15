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
        # Paths are recorded RELATIVE to the repository root. An absolute
        # path records the machine the registry was built on, not the
        # member, so a committed registry would name trees that exist
        # nowhere else -- and the probe would report every member of
        # somebody else's checkout "unavailable". `load` rehydrates them.
        tree = LINEAGES / f"lineages-{run}" / family
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
                    "earned_root": current, "path": "src",
                    "package": "reticuli"})
    members.sort(key=lambda m: m["id"])
    return {"schema": SCHEMA, "name": "reticuli", "current_root": current,
            "members": members, "retired": retired, "refused": refused,
            "note": "members are members OF current_root; retired members must "
                    "be re-earned rather than inherited"}


#: Interpreters the primary claim's host contract admits. `requires =
#: ["python>=3.11"]` is a declared obligation, so every one of these is a
#: deployment the claim permits, and the claim is responsible for behaving the
#: same way on all of them.
INTERPRETERS = ("python3.11", "python3.13", "python3.14")

#: The jq family: three independent implementations of one documented
#: language, specified by somebody else. A foreign population is the control
#: for the contamination the reticuli population cannot escape -- there,
#: criteria and candidates share an author lineage.
JQ_FAMILY = (("jq", "jq"), ("gojq", "gojq"), ("jaq", "jaq"))


def deployment(repo=".", interpreters=INTERPRETERS):
    """The authored implementation under each interpreter its claim admits.

    This population does not vary the implementation; it varies the host. Each
    entry is the same bytes, so a behavioural difference between them is not a
    difference between implementations but the root failing to determine
    behaviour across the host range it declares. It is also the one population
    that survives a root move, because the member is the authored tree and it
    always carries the current root.
    """
    repo = Path(repo)
    current = _repo_root(repo)
    members = [{"id": f"shipped@{name.replace('python', 'py')}", "run": "shipped",
                "family": "authored", "earned_root": current,
                "path": "src", "package": "reticuli",
                "driver": "python-package", "python": name}
               for name in interpreters]
    return {"schema": SCHEMA, "name": "deployment", "current_root": current,
            "members": members, "retired": [], "refused": [],
            "note": "one implementation, several hosts its claim permits; a "
                    "split here is host dependence the root does not pin"}


def jq(repo="."):
    """Three independent implementations of the jq language.

    Membership here is not relative to a reticuli root -- nobody sealed these
    -- so the registry records the language version each one claims instead,
    and `current_root` names the corpus the population is read against rather
    than an identity. Treat it as a population, never as a claim.
    """
    corpus = Path("research") / "external" / "jq" / "corpus"
    members = [{"id": name, "run": "external", "family": name,
                "earned_root": JQ_POPULATION, "path": str(corpus),
                # `--` ends the flags. Without it a program beginning with a
                # dash is read as an option by whichever member's parser gets
                # there first, and CLI parsing masquerades as a semantic
                # difference: `-0` looked like a three-way split until the
                # separator turned it into unanimous agreement.
                "command": command, "driver": "process", "flags": ["-c", "--"]}
               for name, command in JQ_FAMILY]
    return {"schema": SCHEMA, "name": "jq", "current_root": JQ_POPULATION,
            "members": members, "retired": [], "refused": [],
            "note": "a foreign population: specified by somebody else, so "
                    "criteria and candidates share no author lineage"}


#: A population of implementations nobody sealed carries no root. The registry
#: requires one, so this constant stands in its place and says what it is.
JQ_POPULATION = "external:" + "jq-language".ljust(55, "-")


def _repo_of(registry):
    """The repository a registry was built against, inferred from where the
    registry sits: `<repo>/<companion>/population/<name>.json`.

    The search for a manifest starts ABOVE the companion, and that is the
    whole subtlety. Zeta is a claim itself and carries its own manifest, so
    a nearest-ancestor search finds the companion and resolves every member
    one directory too deep -- which is how this was first written, and what
    the foreign-checkout test caught.
    """
    here = Path(registry).resolve()
    start = here.parents[2] if len(here.parents) > 2 else here.parent
    for candidate in (start, *start.parents):
        if (candidate / ".reticuli" / "manifest.json").is_file():
            return candidate
    return start


def load(path, repo=None):
    """Read a registry and make its member paths usable HERE.

    Recorded paths are repository-relative, so the same registry means the
    same members on any checkout. An absolute path is left exactly as it
    is: registries written before this rule carry them, and a reader that
    silently reinterpreted them would move a member without saying so.
    """
    data = json.loads(Path(path).read_text())
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported population schema")
    base = Path(repo) if repo is not None else _repo_of(path)
    # Controls too: a refused or retired tree is probed alongside the
    # members, so an unresolved path there reports a control as
    # unreachable and quietly removes it from the comparison.
    for group in ("members", "retired", "refused"):
        for member in data.get(group, []) or []:
            recorded = member.get("path")
            if isinstance(recorded, str) and recorded and not Path(recorded).is_absolute():
                member["path"] = str(base / recorded)
    if not data["members"]:
        raise ValueError("population has no current-root members")
    seen = {m["id"] for m in data["members"]}
    if len(seen) != len(data["members"]):
        raise ValueError("population repeats a member id")
    for member in data["members"]:
        if member["earned_root"] != data["current_root"]:
            raise ValueError(f"{member['id']} is not a member of current_root")
    return data
