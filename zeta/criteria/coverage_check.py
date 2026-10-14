"""A redundancy verdict must be earned, and a false kill must be impossible.

Coverage decides which pressure is worth a signature, so the ways it can be
wrong matter more than the ways it can be right.

A FALSE KILL is the dangerous direction. Reporting a mutant as killed when the
criteria never caught it reads as "already pinned", which quietly empties the
queue of exactly the findings worth having. The room staged for a mutant run
is a subset of the repository, so any criterion needing an omitted file would
fail identically against every mutant -- and against the unmutated tree. That
is why the baseline runs first and why a baseline that cannot earn the gate
invalidates the whole report rather than producing one.

A FALSE SURVIVAL is the loud direction: it sends a signature after a gap that
is not there. The expectation column catches it. An operator declared `killed`
that lives, or `survives` that dies, contradicts the instrument's own stated
belief, and a contradiction is reported rather than averaged away.
"""

import sys
from pathlib import Path

# The claim directory, which is this file's parent. A sandboxed audit
# materialises the claim AS the workspace root, so an import reaching
# one level further up works in the repository and fails cold.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import coverage as coveragelib, mutants as mutantlib


def check(condition, why):
    if not condition:
        raise SystemExit(f"coverage_check: {why}")


def report(killed, surviving, digest="d" * 64):
    rows = [{"control": name, "killed": True, "by": ["criteria/x.py"],
             "breaks": "x", "target": "t", "expect": "killed",
             "contradicts_expectation": False} for name in killed]
    rows += [{"control": name, "killed": False, "by": None, "breaks": "x",
              "target": "t", "expect": "unknown",
              "contradicts_expectation": False} for name in surviving]
    return {"schema": "zeta.coverage.1", "criteria_digest": digest,
            "baseline": {"control": "baseline", "killed": False},
            "killed": sorted(killed), "surviving": sorted(surviving),
            "contradictions": [], "rows": rows}


def finding(discriminates):
    return {"disposition": "agreement", "lane": "contraction",
            "rank": len(discriminates), "discriminates": list(discriminates)}


COVER = report(["mutant:a", "mutant:b"], ["mutant:c"])

# A pressure separating only already-killed mutants buys nothing: the criteria
# that would catch those implementations exist. It is redundant, not novel.
done = coveragelib.annotate(finding(["mutant:a", "mutant:b"]), COVER)
check(done["coverage"]["redundant"], "separating only killed mutants is redundant")
check(not done["coverage"]["novel"], "a redundant pressure is not novel")
check(done["coverage"]["separates_surviving"] == [],
      "a redundant pressure separates no survivor")

# A pressure separating a survivor is a genuine free click: the behaviour it
# covers is one the root currently admits an implementation for.
new = coveragelib.annotate(finding(["mutant:a", "mutant:c"]), COVER)
check(new["coverage"]["novel"], "separating a survivor is novel")
check(not new["coverage"]["redundant"], "a novel pressure is not redundant")
check(new["coverage"]["separates_surviving"] == ["mutant:c"],
      "the survivor it separates is named")

# A pressure that separates nothing was never ranked. It is neither redundant
# nor novel, and claiming either would be an opinion the measurement does not
# support.
blunt = coveragelib.annotate(finding([]), COVER)
check(not blunt["coverage"]["redundant"] and not blunt["coverage"]["novel"],
      "an unranked pressure is neither redundant nor novel")

# The verdict is relative to the criteria that produced it, so the digest must
# travel with it: re-pin a criterion and the judgement is made again.
check(new["coverage"]["criteria_digest"] == COVER["criteria_digest"],
      "a redundancy verdict carries the criteria that justified it")
check(coveragelib.annotate(finding(["mutant:c"]), report(
          [], ["mutant:c"], digest="e" * 64))["coverage"]["criteria_digest"]
      == "e" * 64, "a different criteria set yields a different verdict stamp")

# Annotation must not disturb the classification. Redundancy is advice about
# whether to spend a signature, never a change to what was found.
original = finding(["mutant:a"])
annotated = coveragelib.annotate(original, COVER)
for field in ("disposition", "lane", "rank", "discriminates"):
    check(annotated[field] == original[field],
          f"annotation must not alter {field}")

# An unsupported schema is refused rather than read optimistically.
try:
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "coverage.json"
        path.write_text(json.dumps({**COVER, "schema": "zeta.coverage.99"}))
        coveragelib.load(path)
except ValueError as exc:
    check("unsupported coverage schema" in str(exc), f"wrong refusal: {exc}")
else:
    raise SystemExit("coverage_check: read an unsupported coverage schema")

# Every operator must declare an expectation, and at least one must be the
# positive control. Without an operator that MUST live, a report of "every
# mutant killed" cannot be told apart from a harness that cannot detect
# survival at all -- and the first version of this instrument was exactly
# that: four operators, all expected to die, all dying.
expectations = [row[5] for row in mutantlib.OPERATORS]
check(all(e in ("killed", "survives", "unknown") for e in expectations),
      "every operator declares killed, survives or unknown")
check("survives" in expectations,
      "at least one operator must be a positive control that has to live")
check("killed" in expectations, "at least one operator must have to die")
names = [row[0] for row in mutantlib.OPERATORS]
check(len(names) == len(set(names)), "operator names must be distinct")

print("coverage-ok")
