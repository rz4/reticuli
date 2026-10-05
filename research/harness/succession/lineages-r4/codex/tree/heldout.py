"""Run an additional check against a sealed claim's present build."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._kernel import recipe


def evaluate(directory, command, *, files=None):
    """Run an independent gate in a disposable copy of the claim's bytes."""
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    parsed = kernel.load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        kernel._copy_recipe_room(directory, room, parsed)
        for name, source in (files or {}).items():
            target = os.path.join(room, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        result = kernel.run_gate(command, room, parsed)
    return {"ok": result["status"] == "ok", "status": result["status"],
            "root": checked["root"], "quarantine": result.get("quarantine")}


heldout = evaluate
