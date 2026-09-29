"""Run an additional, caller supplied check against a claim realization."""

from __future__ import annotations

from . import kernel


def run(directory: str, command: str) -> dict:
    """Execute a held-out command with the same gate confinement rules."""
    if not isinstance(command, str) or not command:
        raise ValueError("held-out command must be nonempty text")
    verification = kernel.verify(directory)
    if not verification["ok"]:
        raise kernel.ClaimError("claim identity changed")
    outcome = kernel.run_gate(command, directory)
    return {"ok": outcome["status"] == "ok", **outcome}


def heldout(directory: str, command: str) -> dict:
    """Alias for :func:`run` for callers naming the kind of check."""
    return run(directory, command)
