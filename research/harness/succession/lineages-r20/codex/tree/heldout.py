"""Run an independent held-out check against an existing claim build."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel


def check(directory, command, files=None):
    """Judge a command in a disposable copy, leaving the claim untouched."""
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        shutil.copytree(directory, room, dirs_exist_ok=True)
        for name, source in (files or {}).items():
            if os.path.isabs(name) or ".." in name.split("/"):
                raise kernel.ClaimError("unsafe held-out path")
            target = os.path.join(room, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        return kernel.run_gate(command, room, kernel.load_recipe(directory))


heldout = check
