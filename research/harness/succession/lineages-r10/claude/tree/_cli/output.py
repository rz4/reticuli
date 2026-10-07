"""reticuli._cli.output: the --json envelope and the one-voice error line.

Every command ends one of two ways: `_finish` prints its result, either
as the five-field JSON envelope (`command`, `ok`, `status`, `root`,
`data`) a script can parse, or as a short human line; `_err` prints a
refusal to stderr in one voice, `ret: <verb>: <fact>`, so every failure
reads the same regardless of which verb raised it.

The rest of this module is the small human-terminal vocabulary the
surface layer's commands share: a progress notice, a yes/no prompt, one
formatted line, a path made relative to the caller's cwd, and a block of
warnings. None of it is reached when `--json` is set.

Stdlib only.
"""
import json
import os
import sys

_COLOR_CODES = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "bold": "1"}


def _rel(path: str, base: str = None) -> str:
    """`path`, relative to `base` (default: the current directory) --
    or `path` itself when the two share no common root (e.g. different
    drives), since a display helper must never raise."""
    try:
        return os.path.relpath(path, base or os.getcwd())
    except ValueError:
        return path


def _use_color(args) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _line(text: str, *, color: str = None, enabled: bool = True, stream=None) -> None:
    """Print one line, wrapped in `color`'s ANSI code when `enabled`."""
    stream = stream or sys.stdout
    if color and enabled and color in _COLOR_CODES:
        text = f"\x1b[{_COLOR_CODES[color]}m{text}\x1b[0m"
    print(text, file=stream)


def _warn_block(lines, title: str = None) -> None:
    """A block of warning lines on stderr, each on its own line."""
    if title:
        sys.stderr.write(f"warning: {title}\n")
    for line in lines:
        sys.stderr.write(f"  - {line}\n")


def _confirm(prompt: str, default: bool = False) -> bool:
    """A yes/no prompt on stdin; an unreadable or empty answer takes
    `default` rather than failing the command outright."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


class _Progress:
    """A notice around a long-running step, on stderr; silent when
    `enabled` is false (e.g. `--json`, or a non-interactive stream)."""

    def __init__(self, label: str, enabled: bool = True):
        self.label = label
        self.enabled = enabled

    def __enter__(self):
        if self.enabled:
            sys.stderr.write(f"{self.label} ...\n")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.enabled:
            sys.stderr.write(f"{self.label}: {'failed' if exc_type else 'done'}\n")
        return False


def _finish(cmd: str, data, ok: bool, status: str, args, root: str = None):
    """End a command: the --json envelope, or a short human line.

    `root` defaults to `data["root"]` when `data` is a dict and no
    override is given -- most commands' result already carries the
    claim's root, and the envelope only needs to say so once more at
    the top level.
    """
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}

    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
        return envelope

    color_on = _use_color(args)
    marker = "ok" if ok else "refused"
    _line(f"{cmd}: {marker} ({status})", color="green" if ok else "red", enabled=color_on)
    if root:
        _line(f"  root: {root}")
    if getattr(args, "verbose", False) and isinstance(data, dict):
        for key, value in sorted(data.items()):
            if key == "root":
                continue
            _line(f"  {key}: {value}")
    return envelope


def _err(cmd: str, fact: str) -> None:
    """A refusal, in one voice: `ret: <verb>: <fact>`, on stderr."""
    sys.stderr.write(f"ret: {cmd}: {fact}\n")
