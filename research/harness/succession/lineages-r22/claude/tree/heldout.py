"""Surface: whether a claim's gates actually depend on each pinned input
they declare (spec/layers.md: "measuring a claim's strength").

`coverage` removes one declared input at a time from a scratch copy of the
claim and re-runs every gate there. A gate that still passes without an
input never exercised it: the input is declared but not load-bearing. This
is a different question from mutation testing (`assess.py`, which asks
whether the gates can tell the *implementation* apart from a near miss) --
`coverage` asks the same question of the *pinned inputs* the gates are
handed.
"""
import os
import shutil
import tempfile

from . import kernel


def coverage(d: str) -> dict:
    recipe = kernel.load_recipe(d)
    inputs = list(recipe.get("claim", {}).get("inputs", []))
    gates = [s for s in recipe.get("step", []) if s.get("kind") == "gate"]

    result = {}
    for name in inputs:
        room = tempfile.mkdtemp()
        try:
            shutil.copytree(d, room, dirs_exist_ok=True,
                             ignore=shutil.ignore_patterns(kernel.STORE))
            target = os.path.join(room, name)
            if os.path.isfile(target):
                os.remove(target)
            passes_without = True
            for step in gates:
                outcome = kernel.run_gate(step["run"], room, recipe)
                if outcome["status"] != "ok":
                    passes_without = False
                    break
            result[name] = {"load_bearing": not passes_without}
        finally:
            shutil.rmtree(room, ignore_errors=True)
    return result
