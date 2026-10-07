"""Consistent human and JSON output for command line operations."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the caller's working directory when possible."""
    if path is None:
        return None
    return os.path.relpath(os.fspath(path), base or os.getcwd())


def _err(verb, fact):
    _line(f"ret: {verb}: {fact}", file=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        _line(f"ret: {line}", file=sys.stderr)


def _confirm(prompt):
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


class _Progress:
    """Small stderr progress reporter; safe for use with JSON stdout."""

    def __init__(self, label="", enabled=True):
        self.label = label
        self.enabled = enabled

    def __enter__(self):
        if self.enabled and self.label:
            _line(self.label, file=sys.stderr)
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def update(self, message):
        if self.enabled:
            _line(message, file=sys.stderr)

    def done(self, message=None):
        if message is not None:
            self.update(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit one result, preserving the five-field JSON envelope."""
    if isinstance(data, dict) and root is None:
        root = data.get("root")
    if getattr(args, "json", False):
        _line(json.dumps({"command": command, "ok": bool(ok), "status": status,
                          "root": root, "data": data}, sort_keys=True))
    elif isinstance(data, str):
        _line(data)
    elif isinstance(data, dict):
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
        if getattr(args, "verbose", False):
            for key, value in data.items():
                if key != "root":
                    _line(f"  {key}: {value}")
    else:
        _line(f"{command}: {status}")
    return bool(ok)
