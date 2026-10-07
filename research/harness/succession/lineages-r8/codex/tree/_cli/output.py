"""Consistent terminal and JSON output for claim commands."""

from __future__ import annotations

import json
import os
import sys


def _line(message: object = "", *, file=None) -> None:
    print(message, file=file or sys.stdout)


def _rel(path: os.PathLike[str] | str, base: os.PathLike[str] | str | None = None) -> str:
    """Show a path relative to the caller's working directory when possible."""
    return os.path.relpath(os.fspath(path), os.fspath(base) if base is not None else os.getcwd())


def _err(command: str, fact: object) -> None:
    """Emit a single command-scoped error line to stderr."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(message: object) -> None:
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(prompt: str, *, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """A small, optional progress message for terminal commands."""

    def __init__(self, message: str, *, enabled: bool = True) -> None:
        self.message = message
        self.enabled = enabled

    def __enter__(self):
        if self.enabled:
            _line(self.message, file=sys.stderr)
        return self

    def __exit__(self, _type, _value, _traceback) -> bool:
        return False


def _finish(command: str, data: object, ok: bool, status: str,
            args: object, root: str | None = None) -> dict:
    """Report one result, with a stable five-member JSON envelope."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    else:
        label = str(status or ("ok" if ok else "failed"))
        _line(f"{command}: {label}" + (f" {root}" if root else ""))
        if getattr(args, "verbose", False) and data is not None:
            _line(json.dumps(data, sort_keys=True, indent=2, default=str))
    return envelope
