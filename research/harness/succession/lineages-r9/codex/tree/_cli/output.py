"""The command line's single output and error voice."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the working directory when possible."""
    return os.path.relpath(os.fspath(path), os.fspath(base or os.getcwd()))


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
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """Report optional progress on stderr, never in the JSON stream."""

    def __init__(self, enabled=True):
        self.enabled = enabled

    def __call__(self, message):
        if self.enabled:
            _line(message, file=sys.stderr)

    def update(self, message):
        self(message)

    def finish(self, message):
        self(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit one result; JSON mode has exactly the documented five fields."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        label = f"{command}: {status}"
        if root:
            label += f" {root}"
        _line(label)
        if getattr(args, "verbose", False) and data is not None:
            _line(json.dumps(data, indent=2, sort_keys=True, default=str))
    return envelope
