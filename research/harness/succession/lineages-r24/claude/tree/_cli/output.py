"""The output contract: the `--json` envelope, and the one-voice line a
human reads on the terminal (spec/layers.md "surface").

Every command ends by calling `_finish`, which is the one place that decides
between the two renderings. A refusal ends by calling `_err`, which always
speaks the same sentence: `ret: <verb>: <fact>`, on stderr, no matter which
verb or which layer raised it. Stdlib only.
"""
import json
import os
import sys

from reticuli import render

ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")


def _color_on(args) -> bool:
    """Whether ANSI color is wanted: `args.color` is `always`/`never`/`auto`
    (the default), and `auto` paints only when stdout is a terminal."""
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _line(text: str, args=None, color=None, file=None) -> None:
    """One line of human-facing output, painted when color is wanted."""
    if color and (args is None or _color_on(args)):
        text = render.paint(text, color)
    print(text, file=file or sys.stdout)


def _warn_block(lines, args=None) -> None:
    """One or more warning lines, each prefixed and sent to stderr."""
    if isinstance(lines, str):
        lines = [lines]
    for line in lines:
        _line(f"warning: {line}", args=args, color="yellow", file=sys.stderr)


def _err(cmd: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, always on stderr."""
    print(f"ret: {cmd}: {fact}", file=sys.stderr)


def _rel(path: str) -> str:
    """`path` relative to the current directory, or itself where no
    relative form exists (e.g. a different drive)."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def _confirm(prompt: str, default: bool = False) -> bool:
    """A y/n prompt; an unreadable or empty reply takes the default."""
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        reply = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not reply:
        return default
    return reply in ("y", "yes")


def _finish(cmd: str, data, ok: bool, status: str, args, root=None):
    """Render one command's result: the five-field envelope under
    `--json`, or a single colored summary line otherwise. Returns the
    envelope either way, so a caller can act on it without re-deriving it.

    `root` wins when given explicitly; otherwise it falls back to
    `data["root"]` when `data` is a dict that carries one.
    """
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": cmd, "ok": bool(ok), "status": status, "root": root, "data": data}

    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
        return envelope

    color = "green" if envelope["ok"] else "red"
    word = "ok" if envelope["ok"] else "failed"
    line = f"{cmd}: {word} ({status})"
    if root:
        line += f" {render.short(root)}"
    _line(line, args=args, color=color)

    if getattr(args, "verbose", False) and isinstance(data, dict):
        for key in sorted(data):
            _line(f"  {key}: {data[key]}", args=args)

    return envelope


class _Progress:
    """A long-running step's start/finish line (`rebuild`, `audit`,
    `crosscheck`) -- a context manager so the finishing line always prints,
    success or failure, without every caller repeating the bookkeeping."""

    def __init__(self, label: str, args=None):
        self.label = label
        self.args = args

    def __enter__(self):
        _line(f"{self.label}...", args=self.args, color="cyan")
        return self

    def update(self, note: str) -> None:
        _line(f"{self.label}: {note}", args=self.args)

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            _line(f"{self.label}: done", args=self.args, color="green")
        else:
            _line(f"{self.label}: {exc}", args=self.args, color="red")
        return False
