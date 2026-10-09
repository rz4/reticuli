"""reticuli.heldout -- measuring a claim's strength against checks a
producer never saw (spec/layers.md: the surface layer).

A rebuild is judged against the gates its recipe declares; a producer that
specializes to exactly those gates, rather than to the behavior they stand
for, still passes. A held-out check closes that gap from the outside: it is
never added to the recipe, never seen by a producer, and is run only after
the fact, against whatever bytes are already present -- a second, private
opinion about whether the claim generalizes.

This module never touches a claim's recipe or manifest; it only materializes
a scratch copy of the bytes present and runs extra gate commands against it.
"""
import os
import shutil
import tempfile

from reticuli import kernel


def run_heldout(d: str, checks) -> list:
    """Run every held-out check in `checks` (an iterable of `(name, run)`
    pairs) against a scratch copy of `d`'s present bytes. Returns one result
    per check, in order, never mutating `d` or its store."""
    parsed = kernel.load_recipe(d)
    room = tempfile.mkdtemp(prefix="reticuli-heldout-")
    results = []
    try:
        for name in os.listdir(d):
            if name == kernel.STORE:
                continue
            src = os.path.join(d, name)
            dst = os.path.join(room, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        for name, run in checks:
            res = kernel.run_gate(run, room, parsed)
            results.append({"name": name, "status": res["status"],
                             "quarantine": res["quarantine"]})
    finally:
        shutil.rmtree(room, ignore_errors=True)
    return results


def heldout_rate(results) -> float:
    """The fraction of held-out checks that passed; `0.0` for an empty
    list -- an unmeasured claim earns no credit for strength it was never
    asked to show."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("status") == "ok")
    return passed / len(results)
