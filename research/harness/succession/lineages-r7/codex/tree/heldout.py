"""Run an additional, unpinned check against a present claim build.

Held-out results are observations. They do not alter the claim's root or its
sealed verdicts.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import declared_inputs, safe_path


def run(directory, check, command, *, timeout=None):
    """Run a check file beside declared files in a disposable room."""
    recipe = kernel.load_recipe(directory)
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        names = declared_inputs(recipe, directory)
        names += [step["output"] for step in recipe.get("step", [])
                  if step["kind"] == "produce"]
        for name in dict.fromkeys(names):
            source = safe_path(directory, name)
            if os.path.isfile(source):
                destination = safe_path(room, name)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(source, destination)
        check_name, check_path = check
        destination = safe_path(room, check_name)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(check_path, destination)
        gate_recipe = dict(recipe)
        if timeout is not None:
            gate_recipe["claim"] = dict(recipe["claim"], gate_timeout=timeout)
        return kernel.run_gate(command, room, gate_recipe)
