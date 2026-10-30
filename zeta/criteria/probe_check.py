"""The probe must run the MEMBER's own code, and refuse when it cannot.

A behavioural probe is worth exactly what its isolation is worth. If a member
can be made to answer with code that is not its own -- the editable install's
shipped kernel resolving a reconstruction's absolute `from reticuli._kernel
import ...` -- the probe reports a lie that re-earns cleanly, and a grade-2
measurement built on it is worthless. This happened: a probe loaded a trial
under the wrong name and reported the shipped kernel's behaviour as the
trial's (research/harness/closure/grade2-the-crown-jewel.md).

These controls run against built fixtures, never the live population. Three of
them, because the skill's rule holds here too -- a battery without a control
that must FAIL cannot be told from a harness that cannot detect failure:

  RESOLUTION (positive)  a member staged correctly answers with its OWN code,
      even though an ambient `reticuli` (the editable install this very check
      runs under) could have answered instead.
  CONTAINMENT (negative) a member whose probed function is really foreign code
      -- re-exported from the standard library -- is REFUSED as misresolved,
      not run and reported.
  ABSENCE                a call the member does not define is `absent`, not a
      crash and not a silent pass.

    python3 zeta/criteria/probe_check.py        (from the repository root)
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import probe


def check(condition, why):
    if not condition:
        raise SystemExit(f"probe_check: {why}")


def member(base, name, kernel_src, extra=None):
    """Build a fixture member: <base>/<name>/pkg/ as a package named `pkg`."""
    pkg = Path(base) / name / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "kernel.py").write_text(kernel_src)
    for rel, src in (extra or {}).items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src)
    return {"id": name, "path": str(Path(base) / name), "package": "pkg",
            "driver": "python-package", "earned_root": "x" * 64}


tmp = tempfile.mkdtemp(prefix="probe-check-")

# RESOLUTION. The member's `probed` returns the file `reticuli` resolved to.
# Staged correctly it is the member's own __init__, under the member tree. If
# the probe had let the ambient editable install answer -- which it can, this
# check runs under it -- the path would be the shipped src instead. The
# function imports reticuli internals ABSOLUTELY, the exact style that fell
# through to shipped when a member was loaded under another name.
own = member(tmp, "own", (
    "from reticuli import _k as _k\n"
    "def probed():\n"
    "    import os, reticuli\n"
    "    return os.path.realpath(reticuli.__file__)\n"),
    extra={"_k/__init__.py": "tag = 'member'\n"})
r = probe.observe(own, "probed", [])
check(r["kind"] == "value", f"an honest member must answer with a value: {r}")
answered = r["value"].get("plain") or r["value"].get("repr") or ""
own_tree = str((Path(own["path"]) / "pkg").resolve())
check(answered.startswith(own_tree),
      f"the member's OWN code must answer, from {own_tree}, not {answered}")
# And prove the ambient install really could have answered, or the control is
# vacuous: shipped reticuli must be importable here.
import importlib.util
check(importlib.util.find_spec("reticuli") is not None,
      "this check must run with an ambient reticuli, or RESOLUTION proves nothing")

# CONTAINMENT. The probed name is really `json.dumps` -- foreign code whose
# code object lives in the standard library, outside the member tree. The
# driver must refuse it rather than run it and report json.dumps's behaviour.
foreign = member(tmp, "foreign", "from json import dumps as probed\n")
r = probe.observe(foreign, "probed", ["x"])
check(r["kind"] == "misresolved",
      f"a function whose code is foreign must be refused: {r}")
check(r.get("error_type") == "ForeignCode",
      f"the refusal names the reason: {r}")

# ABSENCE. A call the member does not define is reported, never guessed.
r = probe.observe(own, "nonexistent", [])
check(r["kind"] == "absent", f"a missing call is absent: {r}")

print("probe-ok")
