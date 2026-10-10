"""Consistent human and JSON output for command line verbs."""

from __future__ import annotations

import json
import os
import sys


def _rel(path, base=None):
    """Show a path relative to the current directory when possible."""
    base = os.fspath(base) if base is not None else os.getcwd()
    try:
        return os.path.relpath(os.fspath(path), base)
    except (TypeError, ValueError):
        return str(path)


def _line(message="", *, file=None):
    print(message, file=file or sys.stdout)


def _err(command, fact):
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    """Write a warning as one stderr block."""
    _line(f"ret: {message}", file=sys.stderr)


def _confirm(prompt, default=False):
    """Request an explicit yes/no answer from an interactive terminal."""
    if not sys.stdin.isatty():
        return default
    answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """Small progress reporter that stays quiet in machine-readable mode."""

    def __init__(self, args=None):
        self.quiet = bool(getattr(args, "json", False))

    def __call__(self, message):
        if not self.quiet:
            _line(message, file=sys.stderr)

    def update(self, message):
        self(message)


def _finish(command, data, ok, status, args, root=None):
    """Emit the documented five-field envelope or a short human result."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        label = status if status is not None else ("ok" if ok else "failed")
        _line(f"{command}: {label}")
        if getattr(args, "verbose", False) and root:
            _line(f"root: {root}")
    return envelope
