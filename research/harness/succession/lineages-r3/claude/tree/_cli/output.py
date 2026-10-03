"""CLI output: the `--json` envelope, the one-voice error line, and the
small human-readable helpers (`cli.py`) a verb's command function uses to
talk to a terminal.

Every verb ends by calling `_finish`, which either prints the five-field
JSON envelope (`--json`) or a short colored summary line -- never both,
and never any other shape, so a script reading `--json` output always
gets exactly `{command, ok, status, root, data}`.
"""
import json
import os
import sys

_COLOR_CODES = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "bold": "1"}


def _rel(path, base=None):
    """`path` rendered relative to `base` (default: the current directory)
    for display; falls back to the raw path when there is no common root
    (a different drive, or `path` escaping `base` entirely is still shown,
    just not shortened).
    """
    base = base if base is not None else os.getcwd()
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return str(path)


def _paint(text, color, args):
    """`text` wrapped in `color`'s ANSI code, unless `args` asks for no
    color (`args.color == "never"`, or no `args` at all).
    """
    if args is None or getattr(args, "color", "never") == "never" or color is None:
        return text
    code = _COLOR_CODES.get(color)
    if code is None:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _line(text, *, color=None, args=None, file=None):
    """Print one line to `file` (default stdout), colored when `args`
    requests it.
    """
    print(_paint(text, color, args), file=file if file is not None else sys.stdout)


def _warn_block(lines, *, file=None):
    """Print a `warning: ...` line per entry of `lines` (a single string
    is treated as one line) to `file` (default stderr).
    """
    stream = file if file is not None else sys.stderr
    if isinstance(lines, str):
        lines = [lines]
    for line in lines:
        print(f"warning: {line}", file=stream)


def _err(verb, fact):
    """The one-voice error line every refusal speaks in: `ret: <verb>:
    <fact>`, on stderr.
    """
    print(f"ret: {verb}: {fact}", file=sys.stderr)


def _confirm(prompt, *, default=False):
    """Ask a yes/no question on stdin. Returns `default` on EOF or an
    empty reply; otherwise whether the reply starts with `y`.
    """
    suffix = " [Y/n] " if default else " [y/n] "
    try:
        reply = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not reply:
        return default
    return reply.startswith("y")


class _Progress:
    """A minimal progress scope for a long-running verb (`rebuild`,
    `audit`, `crosscheck`): prints a start line and a done/failed line
    under `args.verbose`, nothing animated, nothing under a quiet run.
    """

    def __init__(self, label, *, args=None, file=None):
        self.label = label
        self.args = args
        self.file = file if file is not None else sys.stderr

    def _verbose(self):
        return getattr(self.args, "verbose", False) if self.args is not None else False

    def __enter__(self):
        if self._verbose():
            print(f"... {self.label}", file=self.file)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._verbose():
            print(("failed: " if exc is not None else "done: ") + self.label, file=self.file)
        return False

    def update(self, text):
        """Report an intermediate step under the same label."""
        if self._verbose():
            print(f"... {text}", file=self.file)


def _finish(command, data, ok, status, args, root):
    """The final output of a CLI verb. With `args.json`, print the
    five-field envelope (`command`, `ok`, `status`, `root`, `data`) as one
    JSON line on stdout. Otherwise print a short colored summary line
    (green on `ok`, red otherwise) to stdout.
    """
    if getattr(args, "json", False):
        envelope = {
            "command": command,
            "ok": ok,
            "status": status,
            "root": root,
            "data": data,
        }
        print(json.dumps(envelope, sort_keys=True))
        return
    _line(f"{command}: {status}", color="green" if ok else "red", args=args)
