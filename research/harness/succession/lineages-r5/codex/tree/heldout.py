"""Run a held-out check against the present bytes of a sealed claim."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import safe_path


def check(directory, command, files=None):
    """Judge a copy with additional check files, preserving the sealed claim."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        shutil.copytree(directory, room, dirs_exist_ok=True)
        for name, source in (files or {}).items():
            target = safe_path(room, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        outcome = kernel.run_gate(command, room)
    return {"ok": outcome["status"] == "ok", "status": outcome["status"],
            "root": verified["root"], "detail": outcome.get("stderr", ""),
            "sandbox": outcome.get("quarantine", "none")}
