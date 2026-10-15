"""Consistent command line output for claim operations."""

from __future__ import annotations

import json
import os
import sys


def _line(message="", *, stream=None):
    """Write one human-readable line."""
    print(message, file=sys.stdout if stream is None else stream)


def _rel(path, base=None):
    """Show a local path relative to the current directory when possible."""
    if path is None:
        return ""
    if base is None:
        base = os.getcwd()
    try:
        return os.path.relpath(os.fspath(path), base)
    except (TypeError, ValueError, OSError):
        return str(path)


def _err(command, fact):
    """Report a failure through the command's single stderr voice."""
    _line(f"ret: {command}: {fact}", stream=sys.stderr)


def _warn_block(message):
    """Keep warnings out of machine-readable stdout."""
    if isinstance(message, (list, tuple)):
        for line in message:
            _line(f"ret: warning: {line}", stream=sys.stderr)
    else:
        for line in str(message).splitlines() or [""]:
            _line(f"ret: warning: {line}", stream=sys.stderr)


def _confirm(prompt, default=False):
    """Ask for an explicit terminal confirmation."""
    if not sys.stdin.isatty():
        return default
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(prompt) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """A small stderr progress reporter, silent unless enabled."""

    def __init__(self, enabled=True):
        self.enabled = enabled

    def __call__(self, message):
        if self.enabled:
            _line(message, stream=sys.stderr)

    def write(self, message):
        self(message)

    def close(self):
        pass


def _finish(command, data, ok, status, args, root=None):
    """Present the standard five-field JSON envelope or a short text result."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True, ensure_ascii=False))
    else:
        summary = status if status is not None else ("ok" if ok else "failed")
        _line(f"{command}: {summary}")
        if getattr(args, "verbose", False) and data is not None:
            _line(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False))
    return envelope
