"""Does identity determine acceptance?

Research tooling -- not normative, not pinned. It demonstrates two states
that share a cryptographic identity and disagree about acceptance, which is
the invariant the root is supposed to carry:

    root(C1) == root(C2)  =>  audit(C1, E) == audit(C2, E)

Both cases are recorded in research/audits/2026-11-04-identity-semantics.md.

    PYTHONPATH=src python3 research/harness/identity/step_order.py

Exits 0 when both defects still reproduce, 1 when either has been repaired --
so this file is also the check a repair has to flip.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from reticuli import kernel, reference                       # noqa: E402
from reticuli._kernel import identity, recipe as recipe_mod  # noqa: E402

GATE_READY = '''[[step]]
kind = "gate"
output = "READY"
class = "validated"
run = "printf ready > READY"
'''

GATE_VERDICT = '''[[step]]
kind = "gate"
output = "VERDICT"
class = "validated"
run = "test -f READY && printf ok > VERDICT"
'''

HEAD = '''[claim]
name = "ordertest"
format = 4
inputs = []

'''


def _claim(where, first, second):
    """A two-gate claim where the second gate reads what the first writes."""
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "reticuli.toml"), "w") as f:
        f.write(HEAD + first + "\n" + second)
    # the pinned outputs must be present and identical in both, or the roots
    # would differ for a reason that has nothing to do with order
    for name, body in (("READY", "ready"), ("VERDICT", "ok")):
        with open(os.path.join(where, name), "w") as f:
            f.write(body)
    return where


def step_order(scratch):
    """Two gate orders, one root, two verdicts."""
    a = _claim(os.path.join(scratch, "A"), GATE_READY, GATE_VERDICT)
    b = _claim(os.path.join(scratch, "B"), GATE_VERDICT, GATE_READY)

    roots, verdicts, order = {}, {}, {}
    for name, where in (("A", a), ("B", b)):
        rec = recipe_mod.load_recipe(where)
        order[name] = [g.get("output") for g in recipe_mod.gates(rec)]
        roots[name] = identity.root(rec, where)
        kernel.seal(where)
        report = kernel.audit(where)
        # `ok` is the verdict; a `verdict` key does not exist on this report
        # and reading one silently reported "no difference" in an earlier
        # draft of this script, which is the failure mode it exists to catch
        verdicts[name] = "earned" if report.get("ok") else "failed"

    # the independent second implementation must agree, or the defect would
    # be one kernel's bug rather than the specification's
    ref = {n: reference.root(w) for n, w in (("A", a), ("B", b))}

    print("FINDING 1 -- step order is outside the root and decides acceptance")
    for name in ("A", "B"):
        print(f"  {name}: gates={order[name]}  root={roots[name][:16]}…  "
              f"reference={ref[name][:16]}…  audit={verdicts[name]}")
    same_root = roots["A"] == roots["B"] == ref["A"] == ref["B"]
    split = verdicts["A"] != verdicts["B"]
    print(f"  one root across both orders : {same_root}")
    print(f"  acceptance differs          : {split}")
    print(f"  kernel and reference agree  : {roots['A'] == ref['A']}")
    return same_root and split


def file_mode(scratch):
    """One build digest, two modes, and only one of them runs."""
    where = os.path.join(scratch, "mode")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "reticuli.toml"), "w") as f:
        f.write('''[claim]
name = "modetest"
format = 4
inputs = ["check.sh"]

[[step]]
kind = "produce"
output = "run.sh"
class = "generated"

[[step]]
kind = "gate"
output = "OK"
class = "validated"
run = "sh check.sh"
''')
    run = os.path.join(where, "run.sh")
    with open(run, "w") as f:
        f.write("#!/bin/sh\necho hi\n")
    with open(os.path.join(where, "check.sh"), "w") as f:
        f.write("#!/bin/sh\n./run.sh > /dev/null && printf ok > OK\n")
    with open(os.path.join(where, "OK"), "w") as f:
        f.write("ok")

    os.chmod(run, 0o755)
    executable = identity.build_digest(where)
    os.chmod(run, 0o644)
    plain = identity.build_digest(where)

    print("\nFINDING 2 -- the build digest is silent about the mode")
    print(f"  mode 755 : {executable[:32]}…")
    print(f"  mode 644 : {plain[:32]}…")
    print(f"  digest unmoved by chmod : {executable == plain}")
    print("  (export/import and ret pull both drop this bit in transport --")
    print("   see research/audits/2026-11-04-manual-population-audit.md)")
    return executable == plain


def main():
    scratch = tempfile.mkdtemp(prefix="reticuli-identity-")
    try:
        one = step_order(scratch)
        two = file_mode(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    if one or two:
        print("Both states above share an identity and differ in behaviour.")
        print("The invariant root(C1)==root(C2) => audit(C1)==audit(C2) does "
              "not hold.")
        return 0
    print("Neither defect reproduces: identity now determines acceptance for "
          "both cases. Update the audit record.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
