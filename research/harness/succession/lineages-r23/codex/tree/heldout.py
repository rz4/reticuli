"""Run a private, additional check against present claim bytes."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._util import safe_path
from . import registry


def check(directory, script, *, command=None):
    """Run *script* in a temporary copy and report its verdict.

    The held-out script stays outside the claim's root and is never copied
    back to the original directory.
    """
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    kernel._hash_file(script)
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        registry._copy_claim(directory, room)
        name = "heldout_check.py"
        target = safe_path(room, name)
        shutil.copyfile(script, target)
        result = kernel.run_gate(command or f"python3 {name}", room)
    return {"ok": result["status"] == "ok", "status": result["status"],
            "root": verified["root"], "quarantine": result.get("quarantine"),
            "stderr": result.get("stderr", "")}


assess = check
