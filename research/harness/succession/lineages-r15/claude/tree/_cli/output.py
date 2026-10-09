"""CLI output: the `--json` envelope and the one-voice human line.

Every verb ends by calling `_finish`: with `args.json` it emits the
documented five-field envelope (`command`, `ok`, `status`, `root`, `data`);
otherwise a short line for a terminal. A refusal always speaks through
`_err`: one line on stderr, `ret: <verb>: <fact>` -- a plain statement of
what happened, never a stack trace and never a question.

Stdlib only.
"""
import json
import os
import sys
import time

ENVELOPE_KEYS = ("command", "ok", "status", "root", "data")


def _rel(path: str, base: str = None) -> str:
    """`path` relative to `base` (default: the current directory), for
    display; `path` itself when the two share no common root."""
    base = base or os.getcwd()
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _use_color(args) -> bool:
    mode = getattr(args, "color", "auto") if args is not None else "never"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(code: str, s: str, enabled: bool) -> str:
    return f"\033[{code}m{s}\033[0m" if enabled else s


def _line(msg: str, args=None, *, bold: bool = False, dim: bool = False,
          stream=None) -> None:
    """Print one line, colored when `args` says the terminal wants it."""
    stream = stream or sys.stdout
    enabled = _use_color(args)
    if bold:
        msg = _paint("1", msg, enabled)
    elif dim:
        msg = _paint("2", msg, enabled)
    print(msg, file=stream, flush=True)


def _warn_block(lines, args=None) -> None:
    """A multi-line warning on stderr, each line marked so the block reads
    as one unit rather than scattered chatter."""
    for ln in lines:
        _line(f"warning: {ln}", args, dim=True, stream=sys.stderr)


def _confirm(prompt: str) -> bool:
    """Ask a yes/no question on stdin; anything but an explicit yes is no."""
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return reply.strip().lower() in ("y", "yes")


def _err(cmd: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, on stderr."""
    print(f"ret: {cmd}: {fact}", file=sys.stderr, flush=True)


def _finish(cmd: str, data, ok: bool, status: str, args, root: str = None) -> None:
    """End a verb's run: the `--json` envelope, or a short human line.

    `root` defaults to `data["root"]` when `data` is a dict carrying one,
    so a caller that already built its result around that key need not
    repeat it.
    """
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if getattr(args, "json", False):
        envelope = {"command": cmd, "ok": ok, "status": status,
                    "root": root, "data": data}
        print(json.dumps(envelope, sort_keys=True))
        return
    word = "ok" if ok else "refused"
    head = f"ret: {cmd}: {word}"
    if status:
        head += f" ({status})"
    if root:
        head += f" {root[:8]}"
    _line(head, args, bold=ok)


class _Progress:
    """A verb's running commentary on stderr: one line per step, so a
    redirected log stays readable (no spinner, nothing overwritten in
    place). Used as a context manager so a verb cannot forget to report
    how its span of work ended.
    """

    def __init__(self, label: str, args=None, stream=None):
        self.label = label
        self.args = args
        self.stream = stream or sys.stderr
        self._started = None

    def __enter__(self):
        self._started = time.monotonic()
        _line(f"{self.label} ...", self.args, dim=True, stream=self.stream)
        return self

    def step(self, msg: str) -> None:
        _line(f"{self.label}: {msg}", self.args, dim=True, stream=self.stream)

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.monotonic() - (self._started or time.monotonic())
        if exc_type is None:
            _line(f"{self.label}: done ({elapsed:.1f}s)", self.args,
                  dim=True, stream=self.stream)
        else:
            _line(f"{self.label}: failed ({elapsed:.1f}s)", self.args,
                  dim=True, stream=self.stream)
        return False
