"""Consistent human and JSON output for command-line verbs."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, stream=None):
    print(message, file=stream or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the current directory when possible."""
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
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """A small stderr progress reporter, quiet for JSON output."""

    def __init__(self, args=None):
        self.quiet = bool(getattr(args, "json", False))

    def update(self, message):
        if not self.quiet:
            _line(message, stream=sys.stderr)

    def __call__(self, message):
        self.update(message)

    def finish(self, message):
        self.update(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit one result; JSON has a fixed five-field envelope."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
    return envelope
