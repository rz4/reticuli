"""Consistent human and JSON output for command-line verbs."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the caller's working directory when possible."""
    return os.path.relpath(os.fspath(path), base or os.getcwd())


def _err(command, fact):
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(question, *, default=False):
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(question) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """A small stderr progress reporter with a quiet JSON mode."""

    def __init__(self, args=None):
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message):
        if not self.quiet:
            _line(message, file=sys.stderr)

    def update(self, message):
        self(message)

    def finish(self, message):
        self(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit the five-member machine envelope or a concise human result."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    elif ok:
        _line(f"{command}: {status}" + (f"  {root}" if root else ""))
    else:
        _err(command, status)
    return envelope

