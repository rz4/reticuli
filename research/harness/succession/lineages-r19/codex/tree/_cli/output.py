"""Consistent human and JSON output for CLI commands."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, stream=None):
    print(message, file=stream or sys.stdout)


def _rel(path, base=None):
    """Display a path relative to the current working directory when possible."""
    if path is None:
        return None
    return os.path.relpath(os.fspath(path), base or os.getcwd())


def _err(command, fact):
    _line(f"ret: {command}: {fact}", stream=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", stream=sys.stderr)


def _confirm(prompt, *, default=False):
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(prompt) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """A small stderr progress reporter, silent for structured output."""

    def __init__(self, args=None):
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message):
        if not self.quiet:
            _line(message, stream=sys.stderr)

    def update(self, message):
        self(message)

    def finish(self, message):
        self(message)


def _finish(command, data, ok, status, args, root=None):
    """Print one complete result; JSON has exactly five top-level members."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if getattr(args, "json", False):
        _line(json.dumps({"command": command, "ok": bool(ok),
                          "status": status, "root": root, "data": data},
                         sort_keys=True))
    else:
        _line(f"{command}: {status}")
        if getattr(args, "verbose", False) and data is not None:
            _line(json.dumps(data, sort_keys=True, indent=2, default=str))
    return 0 if ok else 1
