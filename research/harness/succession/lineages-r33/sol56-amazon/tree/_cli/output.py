"""Consistent output primitives for the command-line interface.

Machine output is one JSON object with a stable five-member envelope.  Human
output and diagnostics remain line oriented; in particular every refusal has
one voice, ``ret: <command>: <fact>``.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import Any


def _colour_enabled(args: Any = None, stream: Any = None) -> bool:
    mode = getattr(args, "color", "auto") if args is not None else "auto"
    if mode in (False, "never", "no", "off"):
        return False
    if mode in (True, "always", "yes", "on"):
        return True
    target = stream if stream is not None else sys.stdout
    return bool(getattr(target, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ


def _line(text: Any = "", *, stream: Any = None, end: str = "\n",
          flush: bool = False) -> None:
    """Write one human-facing line (stdout by default)."""
    print(str(text), file=stream or sys.stdout, end=end, flush=flush)


def _err(command: str, fact: Any) -> None:
    """Emit the CLI's canonical, single-line error diagnostic."""
    # A fact originating in a subprocess can contain several lines.  Keep the
    # prefix unambiguous on each physical line without losing useful detail.
    text = str(fact).strip() or "failed"
    lines = text.splitlines() or [text]
    for item in lines:
        _line(f"ret: {command}: {item}", stream=sys.stderr)


def _rel(path: Any, base: Any = None) -> str:
    """Return a compact path relative to *base* when it is contained there."""
    value = os.path.abspath(os.fspath(path))
    origin = os.path.abspath(os.fspath(base)) if base is not None else os.getcwd()
    try:
        relative = os.path.relpath(value, origin)
    except (OSError, ValueError):
        return value
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return value
    return "." if relative == os.curdir else relative


def _confirm(prompt: str, default: bool = False, *, input_fn=input,
             stream: Any = None) -> bool:
    """Ask a yes/no question; EOF and an empty reply use *default*."""
    suffix = " [Y/n] " if default else " [y/N] "
    target = stream or sys.stderr
    try:
        # ``input`` cannot target stderr, so render the prompt ourselves.
        print(str(prompt) + suffix, file=target, end="", flush=True)
        reply = input_fn()
    except (EOFError, KeyboardInterrupt):
        print(file=target)
        return bool(default)
    answer = str(reply).strip().lower()
    if not answer:
        return bool(default)
    return answer in {"y", "yes"}


def _warn_block(command: str, warning: Any, details: Any = None) -> None:
    """Write a warning and optional indented detail lines to stderr."""
    _line(f"ret: {command}: warning: {warning}", stream=sys.stderr)
    if details is None:
        return
    rows = details if isinstance(details, (list, tuple)) else str(details).splitlines()
    for row in rows:
        _line("  " + str(row), stream=sys.stderr)


class _Progress:
    """Tiny progress reporter which stays silent for JSON/non-interactive use."""

    def __init__(self, label: str = "", args: Any = None, *, stream: Any = None):
        self.label = str(label)
        self.args = args
        self.stream = stream or sys.stderr
        self.enabled = not bool(getattr(args, "json", False)) and bool(
            getattr(self.stream, "isatty", lambda: False)())
        self._shown = False

    def start(self, label: Any = None) -> "_Progress":
        if label is not None:
            self.label = str(label)
        if self.enabled and self.label:
            print(self.label + " …", file=self.stream, end="", flush=True)
            self._shown = True
        return self

    def update(self, label: Any) -> None:
        # Avoid terminal control sequences: progress is deliberately modest
        # and its final result is always emitted by the command itself.
        if self.enabled and not self._shown:
            self.label = str(label)
            self.start()

    def stop(self, status: Any = None) -> None:
        if self._shown:
            print((" " + str(status)) if status is not None else "", file=self.stream)
            self._shown = False

    finish = stop

    def __enter__(self) -> "_Progress":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        self.stop("failed" if exc_type else None)
        return False


def _finish(command: str, data: Any, ok: bool, status: str,
            args: Any, progress: Any = None) -> int:
    """Finish progress and emit either the canonical JSON envelope or text.

    The result's full value lives under ``data``.  ``root`` is repeated at the
    top level because it is the content address common to nearly every verb.
    Exactly these five top-level fields are emitted for ``--json``.
    """
    if progress is not None:
        stopper = getattr(progress, "stop", None) or getattr(progress, "finish", None)
        if callable(stopper):
            stopper(status)

    root = data.get("root") if isinstance(data, Mapping) else None
    envelope = {
        "command": str(command),
        "ok": bool(ok),
        "status": str(status),
        "root": root,
        "data": data,
    }
    if bool(getattr(args, "json", False)):
        # Default JSON settings agree with the project's canonical diagnostic
        # spelling and guarantee one complete line for pipeline consumers.
        _line(json.dumps(envelope, sort_keys=True))
    else:
        root_text = f" {root}" if root else ""
        _line(f"{command}: {status}{root_text}")
        if bool(getattr(args, "verbose", False)) and isinstance(data, Mapping):
            for key in sorted(data):
                if key not in {"ok", "root", "status"}:
                    _line(f"  {key}: {data[key]}")
    return 0 if ok else 1


__all__ = ["_Progress", "_confirm", "_err", "_finish", "_line", "_rel", "_warn_block"]
