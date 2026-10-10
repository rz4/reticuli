"""Consistent human and JSON output for command line verbs."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Show a path relative to the current workspace when possible."""
    if path is None:
        return ""
    base = os.path.abspath(os.fspath(base or os.getcwd()))
    path = os.path.abspath(os.fspath(path))
    relative = os.path.relpath(path, base)
    return relative if relative != "." else "."


def _err(command, fact):
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


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
    """Small stderr progress reporter that keeps stdout machine readable."""

    def __init__(self, label="", *, quiet=False):
        self.label = str(label)
        self.quiet = quiet

    def __enter__(self):
        if self.label and not self.quiet:
            _line(self.label, file=sys.stderr)
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def update(self, message):
        if not self.quiet:
            _line(message, file=sys.stderr)


def _finish(command, result, ok, status, args, message=None):
    """Emit a single JSON envelope or a short human result."""
    data = result if isinstance(result, dict) else {"result": result}
    root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    elif message is not None:
        _line(message)
    elif not ok:
        _err(command, status)
    else:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
    return envelope
