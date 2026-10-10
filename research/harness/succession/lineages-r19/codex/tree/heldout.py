"""Run an extra, unpinned check against the present build of a sealed claim."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel


def check(directory, command, *, files=None):
    """Return an observation from an extra check without changing claim identity."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        shutil.copytree(directory, room, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".reticuli"))
        for name, source in (files or {}).items():
            if os.path.isabs(name) or any(part in ("", ".", "..") for part in name.split("/")):
                raise kernel.ClaimError(f"unsafe heldout path: {name!r}")
            target = os.path.join(room, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
        result = kernel.run_gate(command, room)
    return {"ok": result["status"] == "ok", "status": result["status"],
            "stdout": result["stdout"], "stderr": result["stderr"],
            "root": verified["root"]}
