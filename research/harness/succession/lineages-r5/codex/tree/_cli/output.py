"""Consistent human and JSON output for command line commands."""

from __future__ import annotations

import json
import os
import sys


def _rel(path, base=None):
    """Show a path relative to the current directory when possible."""
    if path is None:
        return ""
    base = os.getcwd() if base is None else base
    try:
        return os.path.relpath(os.fspath(path), base)
    except (TypeError, ValueError):
        return str(path)


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _err(command, fact):
    """Issue one diagnostic line with the command that failed."""
    fact = str(fact).strip().replace("\n", "; ")
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    """Show a warning without making it look like a command failure."""
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(prompt, *, default=False):
    """Ask for an explicit answer when a command needs confirmation."""
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(prompt) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """Minimal progress reporter; JSON output stays machine readable."""

    def __init__(self, args=None):
        self.enabled = not bool(getattr(args, "json", False))

    def line(self, message):
        if self.enabled:
            _line(message, file=sys.stderr)

    def __call__(self, message):
        self.line(message)


def _finish(command, data, ok, status, args, message=None):
    """Emit exactly one JSON envelope or a concise human result."""
    if isinstance(data, dict):
        root = data.get("root")
    else:
        root = None
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    elif message is not None:
        _line(message)
    elif not ok:
        _err(command, status)
    else:
        _line(f"{command}: {status}" + (f"  {root}" if root else ""))
    return envelope
