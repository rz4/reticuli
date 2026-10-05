"""Consistent human and JSON output for claim commands."""

from __future__ import annotations

import json
import os
import sys


def _rel(path):
    """Show a path relative to the working directory when possible."""
    try:
        return os.path.relpath(os.fspath(path))
    except (TypeError, ValueError):
        return str(path)


def _line(message="", *, file=None):
    print(message, file=sys.stdout if file is None else file)


def _err(command, fact):
    print(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message):
    for line in str(message).splitlines() or [""]:
        print(f"ret: warning: {line}", file=sys.stderr)


def _confirm(prompt, *, default=False):
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(str(prompt) + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return bool(default)
    return answer in ("y", "yes")


class _Progress:
    """Optional progress messages, kept out of machine-readable stdout."""

    def __init__(self, args=None):
        self.enabled = bool(getattr(args, "verbose", False))

    def __call__(self, message):
        if self.enabled:
            _line(message, file=sys.stderr)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _finish(command, data, ok, status, args, progress=None):
    """Emit one result; JSON mode always has the same five top-level keys."""
    payload = {"command": command, "ok": bool(ok), "status": status,
               "root": data.get("root") if isinstance(data, dict) else None,
               "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(payload, sort_keys=True))
    else:
        label = status if status is not None else ("ok" if ok else "failed")
        _line(f"{command}: {label}")
        if getattr(args, "verbose", False) and data is not None:
            _line(json.dumps(data, sort_keys=True, indent=2))
    return payload
