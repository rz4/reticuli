"""Consistent terminal and JSON output for CLI commands."""

from __future__ import annotations

import json
import os
import sys


def _rel(path, base=None):
    """Display a path relative to the working directory when practical."""
    if path is None:
        return ""
    if base is None:
        base = os.getcwd()
    try:
        return os.path.relpath(os.fspath(path), base)
    except (OSError, TypeError, ValueError):
        return str(path)


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _err(command, fact):
    """Emit a single, command-attributed error line."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    """Show a warning without mixing it into JSON stdout."""
    lines = str(message).splitlines() or [""]
    for line in lines:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(question, *, default=False):
    """Ask for an explicit yes before an interactive action."""
    if not sys.stdin.isatty():
        return default
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """Small stderr progress reporter; quiet for machine-readable output."""

    def __init__(self, command="", args=None):
        self.command = command
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message):
        if not self.quiet:
            _line(str(message), file=sys.stderr)

    def update(self, message):
        self(message)

    def finish(self, message):
        self(message)


def _finish(command, data, ok, status, args, root=None):
    """Print one result, with a fixed five-field envelope in JSON mode."""
    if getattr(args, "json", False):
        payload = {"command": command, "ok": bool(ok), "status": status,
                   "root": root if root is not None else (data.get("root") if isinstance(data, dict) else None),
                   "data": data}
        _line(json.dumps(payload, sort_keys=True))
    elif isinstance(data, str):
        _line(data)
    elif isinstance(data, dict):
        _line(f"{command}: {status}")
        if getattr(args, "verbose", False):
            _line(json.dumps(data, indent=2, sort_keys=True))
    else:
        _line(f"{command}: {status}")
    return 0 if ok else 1
