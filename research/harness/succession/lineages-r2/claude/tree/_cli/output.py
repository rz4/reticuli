"""reticuli._cli.output: the --json envelope and the console's human voice.

Two audiences read a command's result: a script parsing `--json`, and a
person reading colored text on a terminal. This module is the single place
that decides what either sees, so a command's own code only gathers data
and calls `_finish`; nothing else writes to stdout.

The envelope has exactly five top-level keys: `command`, `ok`, `status`,
`root`, `data`. Every error, from any command, is one line on stderr:
`ret: <verb>: <fact>`.
"""
import json
import os
import sys

_COLOR_CODES = {
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "cyan": "36", "bold": "1", "dim": "2",
}


def _use_color(args) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, color: str, args) -> str:
    if not color or not _use_color(args):
        return text
    code = _COLOR_CODES.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _rel(path: str, base: str = None) -> str:
    """A path for display: relative to `base` (default cwd) when that stays
    inside it, else the path unchanged -- a claim under `/tmp/x` should not
    print as `../../../../tmp/x` just because cwd wandered elsewhere."""
    base = base or os.getcwd()
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def _line(text: str, args, *, color: str = None, file=None) -> None:
    """One line of human-facing output -- a no-op under `--json`, since the
    envelope is the only stdout contract a script may parse."""
    if getattr(args, "json", False):
        return
    print(_paint(text, color, args), file=file or sys.stdout)


def _warn_block(lines, args) -> None:
    """A multi-line warning on stderr, printed as one indented block so it
    reads as a unit rather than scattering into whatever else is logging."""
    if getattr(args, "json", False):
        return
    body = [lines] if isinstance(lines, str) else list(lines)
    if not body:
        return
    print(_paint("warning:", "yellow", args), file=sys.stderr)
    for line in body:
        print(_paint(f"  {line}", "yellow", args), file=sys.stderr)


def _err(cmd: str, msg: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, always on stderr, in
    this exact shape -- a script greps `^ret: <verb>:`, a person reads a
    plain sentence."""
    print(f"ret: {cmd}: {msg}", file=sys.stderr)


def _confirm(prompt: str, args, *, default: bool = False) -> bool:
    """A yes/no prompt on stderr (stdout stays reserved for the envelope).
    `--json` and a non-interactive stdin both answer `default`: there is no
    one to ask, and a hung prompt would be worse than a wrong guess."""
    if getattr(args, "json", False) or not sys.stdin.isatty():
        return default
    suffix = "Y/n" if default else "y/n"
    try:
        answer = input(f"{prompt} [{suffix}] ").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes")


def _finish(cmd: str, data, ok: bool, status: str, args, root=None) -> None:
    """Emit one command's result and nothing else on stdout: the `--json`
    envelope, or a short colored summary for a person. `root` defaults to
    `data["root"]` when `data` is a dict carrying one, since most commands'
    data already names the claim they acted on."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}
    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
        return
    color = "green" if ok else "red"
    summary = f"{cmd}: {status}"
    if root:
        summary += f" ({root[:12]}…)"
    print(_paint(summary, color, args))
    if getattr(args, "verbose", False) and isinstance(data, dict):
        for key, value in sorted(data.items()):
            print(f"  {key}: {value}")


class _Progress:
    """A one-line progress indicator for a long-running verb (`rebuild`,
    `audit`): overwritten in place on a tty, silent under `--json` or when
    stdout is not a terminal, so a redirected log never fills with control
    characters."""

    def __init__(self, label: str, args):
        self._label = label
        self._args = args
        self._active = (not getattr(args, "json", False)) and sys.stdout.isatty()
        self._last = ""

    def __enter__(self):
        if self._active:
            self.update(self._label)
        return self

    def update(self, text: str) -> None:
        if not self._active:
            return
        pad = " " * max(0, len(self._last) - len(text))
        sys.stdout.write(f"\r{text}{pad}")
        sys.stdout.flush()
        self._last = text

    def __exit__(self, exc_type, exc, tb):
        if self._active:
            sys.stdout.write("\r" + " " * len(self._last) + "\r")
            sys.stdout.flush()
        return False
