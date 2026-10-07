"""Run additional, caller supplied checks against a claim's present build."""

from __future__ import annotations

import os
import tempfile

from . import kernel
from ._kernel import core, recipe


def check(directory: str, checks: dict[str, str] | None = None,
          *, gate: str | None = None) -> dict:
    """Run held-out checks in a copy, preserving the original claim bytes."""
    verified = kernel.verify(directory)
    if not verified["ok"]:
        raise kernel.ClaimError("claim identity does not verify")
    parsed = kernel.load_recipe(directory)
    checks = checks or {}
    with tempfile.TemporaryDirectory(prefix="reticuli-heldout-") as room:
        names = [os.path.basename(recipe.recipe_path(directory))]
        names += recipe._inputs(parsed, directory)
        names += [step["output"] for step in parsed.get("step", [])
                  if step["kind"] == "produce"]
        for name in dict.fromkeys(names):
            source = core._safe(directory, name)
            if os.path.isfile(source):
                core._copy_into(source, core._safe(room, name))
        for name, source in checks.items():
            core._copy_into(source, core._safe(room, name))
        if gate is None:
            return {"ok": True, "root": verified["root"], "status": "not_measured"}
        outcome = kernel.run_gate(gate, room, parsed)
        return {"ok": outcome["status"] == "ok", "root": verified["root"],
                "status": outcome["status"], "stdout": outcome.get("stdout", ""),
                "stderr": outcome.get("stderr", "")}


run = check
