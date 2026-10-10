"""Evaluate a claim against an additional, locally supplied check."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import safe_path


def heldout(directory, check, command):
    """Run a held-out check on present bytes in a disposable claim copy.

    The extra check is evidence for the caller; it does not change the sealed
    claim or enter its root.  The command runs through the kernel gate runner.
    """
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity does not hold")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        for base, folders, files in os.walk(directory):
            folders[:] = [name for name in folders if name != kernel.STORE]
            for filename in files:
                source = os.path.join(base, filename)
                name = os.path.relpath(source, directory)
                target = safe_path(room, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)
        target = safe_path(room, os.path.basename(os.fspath(check)))
        shutil.copyfile(check, target)
        verdict = kernel.run_gate(command, room)
    return {"ok": verdict["status"] == "ok", "gate": verdict}


run = heldout
