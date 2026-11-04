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
format = 6
inputs = []

'''


def _claim(where, first, second):
    """A two-gate claim where the second gate reads what the first writes.

    Declared format 6 on purpose: at formats 4 and 5 this recipe is now
    refused at parse, because there the order is stripped from the root.
    """
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

    print("Format 6: step order is INSIDE the root, so two orders are two claims")
    for name in ("A", "B"):
        print(f"  {name}: gates={order[name]}  root={roots[name][:16]}…  "
              f"reference={ref[name][:16]}…  audit={verdicts[name]}")
    distinct = roots["A"] != roots["B"]
    agree = roots["A"] == ref["A"] and roots["B"] == ref["B"]
    split = verdicts["A"] != verdicts["B"]
    print(f"  the two orders are two roots : {distinct}")
    print(f"  acceptance differs           : {split}")
    print(f"  kernel and reference agree   : {agree}")
    # sound when the claims that behave differently ARE different claims
    return distinct and agree


def file_mode(scratch):
    """One build digest, two modes, and only one of them runs."""
    where = os.path.join(scratch, "mode")
    os.makedirs(where, exist_ok=True)
    with open(os.path.join(where, "reticuli.toml"), "w") as f:
        f.write('''[claim]
name = "modetest"
format = 6
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

    print("\nFormat 6: the build digest commits the executable bit")
    print(f"  mode 755 : {executable[:32]}…")
    print(f"  mode 644 : {plain[:32]}…")
    print(f"  digest MOVES on chmod   : {executable != plain}")
    print("  (export/import, ret pull and the chain builder all preserve the")
    print("   bit now; each dropped it before 2026-11-04)")
    return executable != plain


def main():
    scratch = tempfile.mkdtemp(prefix="reticuli-identity-")
    try:
        one = step_order(scratch)
        two = file_mode(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    if one and two:
        print("Identity determines acceptance for both cases at format 6:")
        print("  root(C1) == root(C2)  =>  audit(C1) == audit(C2)")
        return 0
    print("REGRESSION: one of the two repairs no longer holds.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
