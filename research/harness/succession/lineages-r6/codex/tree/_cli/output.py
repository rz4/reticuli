"""Single place for command line output and errors."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _line(message: Any = "", *, file: Any = None) -> None:
    print(message, file=file or sys.stdout)


def _err(command: str, fact: Any) -> None:
    """Report one failure through stderr, with the command in the prefix."""
    _line(f"ret: {command}: {fact}", file=sys.stderr)


def _rel(path: os.PathLike[str] | str, base: os.PathLike[str] | str | None = None) -> str:
    """Show a path relative to the current directory (or a supplied base)."""
    return os.path.relpath(os.fspath(path), os.fspath(base) if base is not None else os.getcwd())


def _warn_block(message: Any) -> None:
    """Keep diagnostic text on stderr, away from machine readable output."""
    for line in str(message).splitlines() or [""]:
        _line(f"ret: warning: {line}", file=sys.stderr)


def _confirm(question: str, *, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(question + suffix).strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes")


class _Progress:
    """Lightweight progress reporter that does not pollute JSON stdout."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def update(self, message: Any) -> None:
        if self.enabled:
            _line(message, file=sys.stderr)

    def __call__(self, message: Any) -> None:
        self.update(message)


def _finish(command: str, data: Any, ok: bool, status: str,
            args: Any, root: str | None = None) -> dict[str, Any]:
    """Emit the stable five-field JSON envelope or a short human result."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": bool(ok), "status": status,
                "root": root, "data": data}
    if getattr(args, "json", False):
        _line(json.dumps(envelope, sort_keys=True))
    elif ok:
        _line(f"{command}: {status}" + (f" {root}" if root else ""))
    else:
        _err(command, status)
    return envelope
