"""A control must never become a member, and a mutant must really be broken.

Controls are how a free click gets ranked, which makes them the one part of
this instrument with an incentive to cheat. If a deliberately broken tree
could land in the member set, it would create splits out of nothing and every
pressure would look like a finding. If a mutant were silently not built, the
pressure it failed to discriminate would look sharp when it is blunt -- which
is exactly what happened the first time: an operator matched twice, was
dropped, and the sweep reported one fewer control without saying so.
"""

import sys
import tempfile
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import mutants as mutantlib, population as poplib, split as splitlib

ROOT = "a" * 64
POPULATION = {"schema": "zeta.population.1", "name": "fixture",
              "current_root": ROOT,
              "members": [{"id": name, "earned_root": ROOT, "path": "/x",
                           "package": "p"} for name in ("one", "two")],
              "retired": [], "refused": []}
PRESSURE = {"schema": "zeta.pressure.1", "source": "fixture", "id": "f/case",
            "clause": "case", "simplicity": 0, "call": "f", "args": [1],
            "specified_reader_behaviour": "n/a", "origin": "fixture"}


def check(condition, why):
    if not condition:
        raise SystemExit(f"control_check: {why}")


def value(payload):
    return {"kind": "value", "value": {"plain": payload}}


# A control cannot create a split, however it answers. Members decide lanes.
agreed = {"one": value(1), "two": value(1)}
with_control = splitlib.classify(POPULATION, PRESSURE, agreed,
                                 {"mutant:x": value(99), "mutant:y": value(98)})
check(with_control["disposition"] == "agreement",
      "controls must not turn an agreement into a split")
check(with_control["lane"] == "contraction", "the lane comes from the members")
check(with_control["rank"] == 2, "each discriminated control raises the rank")
check(with_control["would_evict"] == {}, "a contraction evicts nobody")

# A control that behaves like the members ranks nothing: the pressure would
# not have caught it, and saying otherwise would overstate the click.
blunt = splitlib.classify(POPULATION, PRESSURE, agreed, {"mutant:x": value(1)})
check(blunt["rank"] == 0, "a control inside a member class ranks nothing")

# A control that could not run the pressure never faced it. Counting that as
# discrimination is how an incompatible control manufactures rank: python
# mutants scored against a population of external programs by reporting, four
# times over, that the function did not exist.
for kind in ("absent", "unavailable", "misresolved", "crashed", "timeout"):
    never = splitlib.classify(POPULATION, PRESSURE, agreed,
                              {"mutant:x": {"kind": kind, "error_type": "E",
                                            "error_message": "did not run"}})
    check(never["rank"] == 0,
          f"a control that reported {kind} must rank nothing")
    check(never["discriminates"] == [],
          f"a control that reported {kind} must not count as discriminating")

# A split stays a split, and a control never lowers the eviction cost.
divided = splitlib.classify(POPULATION, PRESSURE,
                            {"one": value(1), "two": value(2)},
                            {"mutant:x": value(3)})
check(divided["disposition"] == "split" and divided["lane"] == "eviction",
      "a control cannot soften a split")
check(divided["rank"] == 0, "ranking is for free clicks, not for decisions")

# A mutant carries no earned root, so the registry must refuse to load one as
# a member even if it is placed there.
smuggled = {**POPULATION,
            "members": POPULATION["members"] +
                       [{"id": "mutant:x", "earned_root": None, "path": "/m",
                         "package": "p"}]}
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "population.json"
    import json
    path.write_text(json.dumps(smuggled))
    try:
        poplib.load(path)
    except ValueError as exc:
        check("not a member of current_root" in str(exc),
              f"a rootless control must be refused as a member: {exc}")
    else:
        raise SystemExit("control_check: loaded a control as a member")

# Every mutant operator must be buildable against the tree it targets, and
# must change it. An operator reported as built but matching nothing would
# make a blunt pressure look sharp.
repo = Path(__file__).resolve().parents[2]
if (repo / "src" / mutantlib.TARGET).is_file():
    with tempfile.TemporaryDirectory() as workspace:
        built, missed = mutantlib.build(repo, workspace)
        check(not missed,
              f"every operator must match its target exactly once: {missed}")
        check(len(built) == len(mutantlib.OPERATORS),
              "every operator must yield a control")
        for control in built:
            check(control["earned_root"] is None,
                  f"{control['id']} must carry no earned root")
            # Each operator names its own file, so compare that one. Comparing
            # a single shared target passed every operator that edited it and
            # failed every operator that did not.
            target = Path(control["target"])
            original = (repo / "src" / target).read_text()
            changed = (Path(control["path"]) / target).read_text()
            check(changed != original, f"{control['id']} must differ from the "
                                       f"tree it mutates, in {target}")
            check("# mutant" in changed, f"{control['id']} must mark its edit")
            # Every other file must be untouched, so a kill is attributable to
            # the one edit rather than to collateral damage.
            for other in {Path(row[1]) for row in mutantlib.OPERATORS} - {target}:
                check((Path(control["path"]) / other).read_text() ==
                      (repo / "src" / other).read_text(),
                      f"{control['id']} must change only {target}, not {other}")

print("control-ok")
