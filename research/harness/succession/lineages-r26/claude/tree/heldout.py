"""Measuring which of a claim's pinned inputs are load-bearing.

Where `assess.py` mutates the generated implementation and asks whether
the gates notice, `heldout` mutates the test side instead: each pinned
input is held out -- removed from a private copy of the claim -- and the
gates are re-run there. A gate that still passes with an input withheld
was never exercising it: the input is declared but inert. A gate that
regresses (or cannot even be formed without the input) shows the input
was load-bearing. The result buckets every declared pinned input into
exactly one of the two -- the test-side analogue of `assess.py`'s
mutation buckets.
"""
import os
import shutil
import tempfile

from reticuli import kernel, _util


def _room_without(d: str, path: str):
    """A private copy of claim `d`, with `path` removed."""
    room = tempfile.mkdtemp(prefix="heldout-")
    dest = os.path.join(room, "c")
    shutil.copytree(d, dest)
    target = _util.safe_path(dest, path)
    if os.path.isfile(target):
        os.remove(target)
    return room, dest


def heldout(d: str) -> dict:
    """Bucket every pinned input of claim `d` into `load_bearing` / `inert`."""
    parsed = kernel.load_recipe(d)
    gate_steps = [s for s in parsed.get("step", []) if s.get("kind") == "gate"]

    load_bearing, inert = [], []
    for path in _util.declared_inputs(d, parsed):
        room, dest = _room_without(d, path)
        try:
            passed = True
            for step in gate_steps:
                outcome = kernel.run_gate(step["run"], dest, parsed)
                if outcome["status"] != "ok":
                    passed = False
                    break
            (inert if passed else load_bearing).append(path)
        except kernel.ClaimError:
            load_bearing.append(path)
        finally:
            shutil.rmtree(room, ignore_errors=True)

    return {"load_bearing": load_bearing, "inert": inert}
