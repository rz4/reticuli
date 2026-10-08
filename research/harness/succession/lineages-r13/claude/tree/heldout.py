"""Held-out generalization: whether a claim's generated code satisfies
tests its own recipe never pinned -- evidence past the gate it was built
to pass (spec/layers.md's surface layer).

Nothing here touches identity: a held-out test can fail without the claim
being wrong, and passing one never advances phase. It is a second opinion,
run in a fresh room so the claim's own sealed bytes are never disturbed.
"""
import os
import shutil
import tempfile

from . import _util
from . import kernel


def run(d: str, tests: dict) -> dict:
    """Materialize `d`'s present bytes into a fresh room, drop in each
    held-out test (`{filename: source path}`), and run it with `python3`.
    Returns `{filename: passed}`, independent of the claim's own gates."""
    recipe = kernel.load_recipe(d)
    room = tempfile.mkdtemp(prefix="reticuli-heldout-")
    results = {}
    try:
        for name in os.listdir(d):
            if name == kernel.STORE:
                continue
            src = os.path.join(d, name)
            if os.path.isfile(src):
                _util.copy_into(src, os.path.join(room, name))
        for name, src in tests.items():
            _util.copy_into(src, os.path.join(room, name))
            result = kernel.run_gate(f"python3 {name}", room, recipe)
            results[name] = result["status"] == "ok"
    finally:
        shutil.rmtree(room, ignore_errors=True)
    return results
