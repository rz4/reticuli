"""Selection must measure members, declare its axes first, and never pick.

Three ways this goes wrong, and all three are cheap to reach.

A NON-MEMBER ON THE FRONTIER. The smallest program is the one that does
nothing, so a frontier that admits non-members ranks programs instead of
answers and recommends the empty one. The project has already measured this:
told to minimise, a producer collapses to the blind prior in a single step.

AXES CHOSEN AFTER THE FACT. A fitness picked once the winner is known is a
story about the winner. The declaration is fixed in source and its digest
travels with every result, so adding an axis afterwards is visible.

A WINNER. One declared axis -- the comments and docstrings that carry why each
guard exists -- runs the other way from size, and no gate can see it at all.
Collapsing the axes into a ranking would quietly recommend trading the only
thing that keeps the tree maintainable by a person.
"""

import sys
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import ledger as ledgerlib, selection as sel, split as splitlib


def check(condition, why):
    if not condition:
        raise SystemExit(f"selection_check: {why}")


def row(name, member=True, total=100, code=60, prose=40, seconds=10.0):
    out = {"candidate": name, "member": member, "audit_seconds": seconds}
    if member:
        out.update(total_bytes=total, code_bytes=code, prose_bytes=prose)
    return out


# Every axis declares a direction and says why it is available for selection
# at all -- an axis the root pins is a criterion, not a preference.
names = [a["name"] for a in sel.AXES]
check(len(names) == len(set(names)), "axis names must be distinct")
for axis in sel.AXES:
    check(axis["better"] in ("lower", "higher"), f"{axis['name']} needs a direction")
    for field in ("measures", "unpinned"):
        check(str(axis.get(field, "")).strip(), f"{axis['name']} must state its {field}")

# The guard against a size-only ranking: at least one axis must prefer MORE.
check(any(a["better"] == "higher" for a in sel.AXES),
      "an axis must run against size, or the frontier recommends amnesia")
check(any(a["name"] == "prose_bytes" and a["better"] == "higher"
          for a in sel.AXES),
      "institutional memory is the axis that runs the other way")

# The declaration is content-addressed, so a later axis is detectable.
before = sel.axes_digest()
check(before == sel.axes_digest(), "the digest is stable for fixed axes")
original = sel.AXES
try:
    sel.AXES = original + [{"name": "late", "better": "lower",
                            "measures": "x", "unpinned": "y"}]
    check(sel.axes_digest() != before,
          "adding an axis must change the declaration digest")
finally:
    sel.AXES = original

# A non-member never reaches the frontier, whatever it would have scored.
tiny = row("empty-program", member=False, seconds=1.0)
tiny.update(total_bytes=1, code_bytes=1, prose_bytes=0)
survey = sel.survey([row("shipped", total=400, code=300, prose=100, seconds=80.0), tiny])
check(survey["frontier"] == ["shipped"],
      f"a non-member must not reach the frontier: {survey['frontier']}")
check(survey["refused"] == ["empty-program"], "a non-member is reported as refused")

# Pareto: strictly worse on every axis is dominated and excluded.
worse = row("worse", total=500, code=400, prose=50, seconds=90.0)
best = row("best", total=400, code=300, prose=100, seconds=80.0)
check(sel.dominates(best, worse), "better on every axis dominates")
check(not sel.dominates(worse, best), "domination is not symmetric")
check(sel.frontier([best, worse]) == ["best"], "a dominated member is excluded")

# A genuine trade keeps BOTH: this is the shape the real measurement found,
# where a reconstruction wins on size and the authored tree wins on prose.
small = row("reconstruction", total=175, code=165, prose=10, seconds=70.0)
rich = row("authored", total=437, code=307, prose=130, seconds=79.0)
check(not sel.dominates(small, rich) and not sel.dominates(rich, small),
      "a trade across axes is not domination")
check(sel.frontier([small, rich]) == ["authored", "reconstruction"],
      "both sides of a real trade stay on the frontier")

# Equal on everything is not domination, so neither is dropped.
check(not sel.dominates(row("a"), row("b")), "equal candidates do not dominate")

# A survey offers no winner and says adoption is not automatic.
full = sel.survey([small, rich])
check("winner" not in full and "best" not in full,
      "a survey must not name a winner")
check("never automatic" in full["adoption"],
      "a survey must say adoption is not automatic")
check(full["axes_digest"] == sel.axes_digest(),
      "a result carries the declaration it was measured against")

# Selection is not a promotion: it moves no root, so it has no lane and
# belongs nowhere in the ledger's vocabulary.
check("selection" not in ledgerlib.LANES, "selection is not a promotion lane")
check("selection" not in splitlib.LANES, "selection is not a pressure lane")
check(not any(k.startswith("selection") for k in ledgerlib.WITNESS_KINDS),
      "selection produces no witness for a signature, because none is needed")

print("selection-ok")
