"""The CLI's output contract: the `--json` envelope, and one-voice errors.

Every verb ends by calling `_finish`, which either prints the five-field
JSON envelope (`command`, `ok`, `status`, `root`, `data`) a scripted caller
can parse, or a short human-readable line when `--json` is absent. Every
refusal goes through `_err`, which always speaks in the same voice: `ret:
<verb>: <fact>`, on stderr, naming what went wrong rather than raising a
raw traceback at the user.

`_line`, `_warn_block`, `_confirm`, and `_Progress` are the human-mode
building blocks a verb's non-JSON path composes from; `_rel` renders a path
for display relative to the caller's cwd, falling back to the absolute
path when there is no sane relative form.
"""
import json
import os
import sys

ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")

_COLORS = {
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _color_enabled(args) -> bool:
    """Whether to colorize: `--color always/never` wins outright, `auto`
    (the default) follows whether stdout is a terminal."""
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, color: str, args) -> str:
    if not color or not _color_enabled(args):
        return text
    return f"{_COLORS[color]}{text}{_COLORS['reset']}"


def _rel(path: str) -> str:
    """`path` for display, relative to the current directory where that is
    a sane rendering; the absolute path otherwise (e.g. a different drive,
    or a relative form that would climb above cwd)."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def _line(args, text: str, *, color: str = None) -> None:
    """One line of human-readable output on stdout, honoring `--color`."""
    print(_paint(text, color, args))


def _warn_block(args, title: str, lines) -> None:
    """A multi-line warning on stderr: a title, then each line indented."""
    print(_paint(title, "yellow", args), file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)


def _confirm(prompt: str) -> bool:
    """Ask the user to type `yes`; anything else, or EOF, refuses."""
    try:
        answer = input(f"{prompt} [yes/no] ")
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


class _Progress:
    """A minimal progress reporter for a long-running verb (`rebuild`,
    `crosscheck`): one line while it runs, interactive terminals only --
    silent under `--json` and silent when stderr is not a terminal, so
    piped or scripted output never gets a stray progress line."""

    def __init__(self, args, label: str):
        self._args = args
        self._label = label
        self._active = not getattr(args, "json", False) and sys.stderr.isatty()

    def __enter__(self):
        if self._active:
            print(f"{self._label} ...", end="", flush=True, file=sys.stderr)
        return self

    def step(self, text: str) -> None:
        if self._active:
            print(f"\n  {text}", end="", flush=True, file=sys.stderr)

    def __exit__(self, exc_type, exc, tb):
        if self._active:
            print(" done" if exc_type is None else " failed", file=sys.stderr)
        return False


def _err(cmd: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, on stderr."""
    print(f"ret: {cmd}: {fact}", file=sys.stderr)


def _finish(cmd, data, ok: bool, status: str, args, root) -> None:
    """End a verb: the `--json` envelope, or a human-readable summary.

    The envelope is exactly `{command, ok, status, root, data}` -- `data`
    is the verb's own result, carried verbatim underneath the four fields
    every verb shares.
    """
    if getattr(args, "json", False):
        envelope = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}
        print(json.dumps(envelope, sort_keys=True))
        return

    mark = "ok" if ok else "FAIL"
    color = "green" if ok else "red"
    head = f"ret: {cmd}: {mark} ({status})"
    if root:
        head += f" {root}"
    _line(args, head, color=color)
    if getattr(args, "verbose", False) and isinstance(data, dict):
        for key in sorted(data):
            _line(args, f"  {key}: {data[key]}")
