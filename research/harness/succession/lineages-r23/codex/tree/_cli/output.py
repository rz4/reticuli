"""Consistent human and JSON output for command line verbs."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _rel(path, base=None):
    """Present paths relative to the working directory where possible."""
    if path is None:
        return None
    base = base or os.getcwd()
    try:
        return os.path.relpath(os.fspath(path), base)
    except (TypeError, ValueError):
        return str(path)


def _err(command, fact):
    """Emit one diagnostic voice on stderr."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    if message:
        for line in str(message).splitlines():
            _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(question, *, default=False):
    """Ask before an interactive action; noninteractive input uses the default."""
    if not sys.stdin.isatty():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """Small stderr progress reporter that keeps stdout machine readable."""

    def __init__(self, command, quiet=False):
        self.command = command
        self.quiet = quiet

    def update(self, message):
        if not self.quiet:
            _line(f"ret: {self.command}: {message}", file=sys.stderr)

    def __call__(self, message):
        self.update(message)


def _finish(command, data, ok, status, args, root=None):
    """Write one result. JSON always has the documented five-field envelope."""
    if not isinstance(data, dict):
        data = {"result": data}
    if root is None:
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
        if getattr(args, "verbose", False):
            _line(json.dumps(data, indent=2, sort_keys=True))
    return 0 if ok else 1
