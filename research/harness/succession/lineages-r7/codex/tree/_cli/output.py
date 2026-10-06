"""Consistent human and JSON output for Reticuli commands."""

from __future__ import annotations

import json
import os
import sys


def _line(message: object = "", *, file=None) -> None:
    print(message, file=file or sys.stdout)


def _err(command: str, fact: object) -> None:
    """Write one diagnostic in the command's voice."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _rel(path: str, base: str | None = None) -> str:
    """Show a path relative to the current workspace when possible."""
    base = os.path.abspath(base or os.getcwd())
    path = os.path.abspath(path)
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _warn_block(lines: object) -> None:
    if isinstance(lines, str):
        lines = [lines]
    for line in lines:
        _line(f"ret: warning: {line}", file=sys.stderr)


class _Progress:
    """Small stderr progress reporter, silent in JSON mode."""

    def __init__(self, args=None):
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message: object) -> None:
        if not self.quiet:
            _line(message, file=sys.stderr)

    def update(self, message: object) -> None:
        self(message)


def _confirm(question: str, args=None) -> bool:
    """Ask for an affirmative answer when a command needs one."""
    if getattr(args, "yes", False):
        return True
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _finish(command: str, data: dict | None, ok: bool, status: str,
            args=None, root: str | None = None) -> dict:
    """Emit the five-field result envelope or a short human summary."""
    payload = data if data is not None else {}
    if root is None and isinstance(payload, dict):
        root = payload.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": payload}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        suffix = f" {root}" if root else ""
        _line(f"{command}: {status}{suffix}")
    return envelope
