"""reticuli._cli.output -- the `--json` envelope shape and the one-voice
error line.

Every verb ends by calling `_finish`: under `--json` it prints exactly one
line, the five-field envelope (`command`, `ok`, `status`, `root`, `data`)
and nothing else, so a caller piping through `json.loads` never has to
skip banner text; otherwise it prints a short human summary, plus any
warnings, to stdout. Every refusal ends by calling `_err`, which always
speaks in one voice regardless of which verb triggered it: `ret: <verb>:
<fact>`, on stderr.

Stdlib only. Never the network.
"""
import json
import os
import sys

ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")

_COLORS = {"red": "31", "green": "32", "yellow": "33", "cyan": "36"}


def _use_color(args) -> bool:
    """Whether to paint output: `args.color` is `always` / `never` / `auto`
    (the default), and `auto` paints only when stdout is a real terminal."""
    mode = getattr(args, "color", "auto") if args is not None else "auto"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, color: str, args) -> str:
    if not _use_color(args):
        return text
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _rel(path: str) -> str:
    """`path` relative to the current directory, for display; the path
    itself, unshortened, if it shares no common root (a different drive
    or mount, where a relative form would be misleading)."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return path
    return path if rel.startswith(os.pardir) else rel


def _line(text: str, args=None, color=None) -> None:
    """One line of human-readable output, painted if `color` and the
    terminal both allow it."""
    if color:
        text = _paint(text, color, args)
    print(text)


def _warn_block(lines, args=None) -> None:
    """A block of warnings, one per line, prefixed and painted yellow, on
    stderr -- so a `--json` caller capturing stdout never sees them mixed
    into the envelope."""
    for line in lines:
        text = _paint(f"warning: {line}", "yellow", args)
        print(text, file=sys.stderr)


def _confirm(prompt: str) -> bool:
    """A y/N prompt; anything but an explicit `y`/`yes` (including EOF, a
    non-interactive stdin) refuses."""
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return reply.strip().lower() in ("y", "yes")


class _Progress:
    """A minimal step-by-step progress reporter. Always writes to stderr,
    never stdout, so a long-running verb's progress never lands inside a
    `--json` envelope; silenced outright when `args.json` is set, since a
    machine reader has no use for it."""

    def __init__(self, args=None):
        self._enabled = not (args is not None and getattr(args, "json", False))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def step(self, text: str) -> None:
        if self._enabled:
            print(f"... {text}", file=sys.stderr)


def _err(command: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, on stderr."""
    print(f"ret: {command}: {fact}", file=sys.stderr)


def _finish(command: str, data, ok: bool, status: str, args, warnings=None) -> int:
    """End a verb: under `--json`, print exactly the five-field envelope
    and nothing else; otherwise print a short human summary (plus any
    warnings). Returns the process exit code (`0` if `ok`, else `1`)."""
    root = data.get("root") if isinstance(data, dict) else None
    envelope = {
        "command": command,
        "ok": bool(ok),
        "status": status,
        "root": root,
        "data": data,
    }
    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
    else:
        color = "green" if ok else "red"
        summary = f"{command}: {status}"
        if root:
            summary += f" ({root})"
        _line(summary, args, color=color)
        if warnings:
            _warn_block(warnings, args)
    return 0 if ok else 1
