"""Run caller supplied checks against a materialized claim.

Held out checks are observations: they are outside the pinned recipe and do
not change the root or the claim's earned gate verdict.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel


def evaluate(directory, commands):
    """Run each command in a copy and return its gate outcomes."""
    if not kernel.verify(directory)["ok"]:
        raise kernel.ClaimError("claim identity mismatch")
    if isinstance(commands, str):
        commands = [commands]
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        shutil.copytree(os.fspath(directory), room, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        parsed = kernel.load_recipe(room)
        for command in commands:
            if not isinstance(command, str):
                raise TypeError("heldout commands must be strings")
            result = kernel.run_gate(command, room, parsed)
            outcomes.append({"command": command, "status": result["status"],
                             "quarantine": result.get("quarantine")})
    return {"ok": all(row["status"] == "ok" for row in outcomes),
            "checks": outcomes}
