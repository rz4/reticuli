"""reticuli.heldout: measuring a claim against what it never pinned.

A claim's gates are its pinned criteria; passing them is necessary but
says nothing about a regrown implementation past the exact behavior
those criteria exercise. `run` executes a check script that is *not*
among the claim's pinned inputs against the claim's present generated
bytes, under the same gate contract the claim's own gates run under
(`kernel.run_gate`: scrubbed environment, sandboxed, bounded), and
reports whether it passed -- without ever writing into the claim
directory or touching its identity.

Stdlib only.
"""
import os
import shutil

from . import kernel


def run(d: str, check: str, *, command: str = None) -> dict:
    """Run held-out check script `check` against claim directory `d`.

    `check` is a path to a script outside `d`'s pinned inputs.
    `command` defaults to `python3 <basename of check>`. The script is
    copied in only for the run and removed afterward; a name collision
    with a file already present in `d` is refused rather than
    overwritten.
    """
    parsed = kernel.load_recipe(d)
    name = os.path.basename(check)
    dst = os.path.join(d, name)
    if os.path.exists(dst):
        raise kernel.ClaimError(
            f"held-out check {name!r} collides with a file already in {d!r}")
    cmd = command or f"python3 {name}"
    shutil.copy2(check, dst)
    try:
        result = kernel.run_gate(cmd, d, parsed)
    finally:
        os.remove(dst)
    return {"ok": result["status"] == "ok", "status": result["status"],
            "quarantine": result.get("quarantine")}
