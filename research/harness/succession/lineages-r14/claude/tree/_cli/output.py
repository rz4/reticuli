"""reticuli._cli.output -- the `--json` envelope and human-readable printing.

Every verb ends in exactly one envelope, `{command, ok, status, root,
data}`: under `--json` it is printed as one line of JSON; otherwise a short
human line goes to stdout, with the full data available under `--verbose`.
Every refusal speaks in one voice -- `ret: <verb>: <fact>`, to stderr, never
a traceback, since a `kernel.ClaimError` is already a reason in its own
words.
"""
import json
import os
import sys

_COLOR_CODE = {"red": "31", "yellow": "33", "green": "32", "cyan": "36"}


def _wants_color(args) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, name: str, args) -> str:
    """`text`, wrapped in `name`'s ANSI code when `args` asks for color."""
    if not name or not _wants_color(args) or name not in _COLOR_CODE:
        return text
    return f"\033[{_COLOR_CODE[name]}m{text}\033[0m"


def _rel(path: str, base: str = None) -> str:
    """`path` for display, relative to `base` (default: the cwd) -- falls
    back to `path` itself across filesystem boundaries, where no relative
    form exists."""
    try:
        return os.path.relpath(path, base or os.getcwd())
    except ValueError:
        return path


def _line(text: str, *, color: str = None, args=None, stream=sys.stdout) -> None:
    """One line of human-readable output, optionally colored."""
    print(_paint(text, color, args), file=stream)


def _warn_block(lines, args=None) -> None:
    """A block of warnings, one per line, prefixed and sent to stderr --
    never fatal, so a caller continues after printing it."""
    for line in lines:
        print(_paint(f"warning: {line}", "yellow", args), file=sys.stderr)


def _confirm(prompt: str) -> bool:
    """A yes/no question on stdin; EOF or anything but `y`/`yes` is no."""
    try:
        answer = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _err(command: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, to stderr."""
    print(f"ret: {command}: {fact}", file=sys.stderr)


class _Progress:
    """A minimal progress note for a long-running verb: a label on entry,
    `done`/`failed` on exit -- one line total, and silent when stdout is
    not a terminal (a redirected/piped run gets no progress noise)."""

    def __init__(self, label: str, stream=sys.stdout):
        self.label = label
        self.stream = stream
        self._active = stream.isatty()

    def __enter__(self):
        if self._active:
            print(f"{self.label}...", end="", flush=True, file=self.stream)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._active:
            print(" failed" if exc_type else " done", file=self.stream)
        return False


def _finish(command: str, result: dict, ok: bool, status: str, args, warnings=None) -> dict:
    """Build the envelope, print it (`--json`: one line of JSON; else a
    short human line, `--verbose` adding the full data), and return it so a
    caller holding the envelope never has to re-derive it."""
    root = result.get("root") if isinstance(result, dict) else None
    envelope = {"command": command, "ok": ok, "status": status, "root": root, "data": result}

    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
    else:
        verb = _paint(command, "green" if ok else "red", args)
        line = f"{verb}: {status}"
        if root:
            line += f" ({root[:12]}…)"
        print(line)
        if getattr(args, "verbose", False) and result is not None:
            print(json.dumps(result, sort_keys=True, indent=2))

    if warnings:
        _warn_block(warnings, args)
    return envelope
