"""Consistent text and JSON output for command-line verbs."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    """Print one line to the selected stream."""
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the working directory when possible."""
    if path is None:
        return None
    return os.path.relpath(os.fspath(path), base or os.getcwd())


def _err(command, fact):
    """Report a failure once, under the verb that failed."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    """Keep a warning on stderr, away from machine-readable output."""
    if message:
        for line in str(message).splitlines():
            _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(prompt, default=False):
    """Ask for an explicit yes before an interactive action."""
    try:
        answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    except EOFError:
        return False
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """A small stderr progress reporter that cannot corrupt JSON stdout."""

    def __init__(self, command="", enabled=True):
        self.command = command
        self.enabled = enabled

    def update(self, message):
        if self.enabled:
            _line(f"ret: {self.command}: {message}" if self.command else str(message),
                  file=sys.stderr)

    def __call__(self, message):
        self.update(message)

    def finish(self, message):
        self.update(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit the five-member command envelope, or a concise text result."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    elif not ok:
        _err(command, status)
    elif getattr(args, "verbose", False):
        _line(json.dumps(data, indent=2, sort_keys=True))
    else:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
    return envelope
