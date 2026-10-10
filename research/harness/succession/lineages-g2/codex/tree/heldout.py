"""Helpers for judging a claim with checks kept outside its recipe."""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel


def run(directory, check, *, command=None):
    """Run one held-out check beside a copy of the present claim bytes.

    The held-out file is copied into a temporary room; it never enters the
    claim root or modifies the caller's directory.
    """
    source = os.path.realpath(os.fspath(directory))
    if not kernel.verify(source)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    check = os.path.realpath(os.fspath(check))
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        shutil.copytree(source, room, dirs_exist_ok=True)
        name = os.path.basename(check)
        target = os.path.join(room, name)
        if os.path.exists(target):
            raise kernel.ClaimError("held-out check collides with a claim file")
        kernel._hash_file(check)
        shutil.copy2(check, target)
        return kernel.run_gate(command or "python3 " + name, room)
