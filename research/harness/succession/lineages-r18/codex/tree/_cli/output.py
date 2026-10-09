"""Consistent human and JSON output for command line operations."""

from __future__ import annotations

import json
import os
import sys


def _rel(path, base=None):
    """Show a path relative to the current directory when possible."""
    if path is None:
        return ""
    return os.path.relpath(os.fspath(path), os.fspath(base) if base else os.getcwd())


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _err(command, fact):
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(question, default=False):
    """Ask for an explicit answer; an unavailable terminal uses *default*."""
    if not sys.stdin.isatty():
        return bool(default)
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(question) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return bool(default)
    return answer in ("y", "yes")


class _Progress:
    """Small stderr progress reporter that stays silent in JSON mode."""

    def __init__(self, command="", args=None):
        self.command = command
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message):
        if not self.quiet:
            _line(f"ret: {self.command}: {message}" if self.command else message,
                  file=sys.stderr)

    update = __call__

    def finish(self, message):
        self(message)


def _finish(command, data, ok, status, args, message=None):
    """Emit one result, with a stable five-member JSON envelope."""
    payload = data if isinstance(data, dict) else {"value": data}
    root = payload.get("root")
    if getattr(args, "json", False):
        _line(json.dumps({"command": command, "ok": bool(ok),
                          "status": status, "root": root, "data": payload},
                         sort_keys=True))
    elif message is not None:
        _line(message)
    else:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
    return 0 if ok else 1
