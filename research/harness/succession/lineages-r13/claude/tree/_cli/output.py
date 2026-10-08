"""The CLI's output contract: the `--json` envelope every verb finishes
through, and the one-voice error line every refusal speaks through.

A verb's human-readable output and its `--json` output are two renderings
of the same envelope -- five fields, always: `command`, `ok`, `status`,
`root`, `data`. Nothing a verb prints bypasses `_finish`; nothing a verb
refuses with bypasses `_err`.
"""
import json
import sys

ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")


def _rel(path: str, base: str = None) -> str:
    """A path for human display: relative to `base` (default: the current
    directory) where that is shorter and meaningful, the given path
    otherwise."""
    import os
    base = base or os.getcwd()
    try:
        rel = os.path.relpath(path, base)
    except ValueError:
        return path
    return rel if not rel.startswith("..") else path


def _line(msg: str, args=None) -> None:
    """One line of human-readable progress; suppressed under `--json`,
    where the envelope is the only output."""
    if args is not None and getattr(args, "json", False):
        return
    print(msg)


def _warn_block(lines, args=None) -> None:
    """A block of warnings, one per line, on stderr -- visible regardless
    of `--json`, since a warning is not the command's result."""
    if not lines:
        return
    if isinstance(lines, str):
        lines = lines.splitlines()
    for line in lines:
        print(f"ret: warning: {line}", file=sys.stderr)


def _confirm(prompt: str) -> bool:
    """A yes/no prompt on stdin; anything but an explicit yes refuses, and
    an unreadable stdin (EOF, piped-shut) refuses rather than hangs."""
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return reply.strip().lower() in ("y", "yes")


class _Progress:
    """A minimal step counter for long-running verbs (`rebuild`, `audit`,
    `crosscheck`); a context manager so a verb's progress reporting cleans
    up on an exception without the verb itself needing a `finally`."""

    def __init__(self, total: int = 0, args=None):
        self.total = total
        self.count = 0
        self.args = args

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def step(self, label: str) -> None:
        self.count += 1
        if self.args is not None and getattr(self.args, "json", False):
            return
        if self.total:
            print(f"[{self.count}/{self.total}] {label}")
        else:
            print(f"-> {label}")


def _err(verb: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, on stderr -- every
    refusal in this tool speaks through this one sentence shape."""
    print(f"ret: {verb}: {fact}", file=sys.stderr)


def _finish(command: str, data: dict, ok: bool, status: str, args, root: str = None) -> dict:
    """Finish a verb: build the envelope, print it (JSON under `--json`,
    one summary line otherwise), and return it so a caller composing verbs
    can inspect what was just printed."""
    data = data if data is not None else {}
    if root is None:
        root = data.get("root")
    envelope = {"command": command, "ok": ok, "status": status, "root": root, "data": data}
    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
    else:
        word = "ok" if ok else "failed"
        _line(f"{command}: {status} ({word})", args=args)
    return envelope
