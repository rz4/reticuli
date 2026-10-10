"""The CLI's output contract: the `--json` envelope and the one-voice
error line, plus the small human-readable helpers the surface prints
through.

Every verb ends by calling `_finish`: under `--json` it prints exactly
one JSON object with five members (`command`, `ok`, `status`, `root`,
`data`) and nothing else on stdout, so a script can pipe the output
straight into `json.loads`. Otherwise it prints a short colored line.
Every refusal goes through `_err`, which speaks in one voice no matter
which verb raised it: `ret: <verb>: <fact>`, on stderr.
"""
import json
import sys

_COLORS = {
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "reset": "\x1b[0m",
}


def _color_enabled(args, file) -> bool:
    mode = getattr(args, "color", "auto") if args is not None else "auto"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return hasattr(file, "isatty") and file.isatty()


def _line(msg: str, *, args=None, color: str = None, file=None) -> None:
    file = file or sys.stdout
    text = msg
    if color and _color_enabled(args, file):
        text = f"{_COLORS.get(color, '')}{msg}{_COLORS['reset']}"
    print(text, file=file)


def _rel(path: str) -> str:
    import os
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def _warn_block(lines, *, args=None, file=None) -> None:
    file = file or sys.stderr
    for line in lines:
        _line(f"warning: {line}", args=args, color="yellow", file=file)


def _confirm(prompt: str, *, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def _err(cmd: str, fact: str, *, file=None) -> None:
    print(f"ret: {cmd}: {fact}", file=file or sys.stderr)


def _finish(cmd: str, data, ok: bool, status: str, args, root) -> dict:
    envelope = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}
    if getattr(args, "json", False):
        print(json.dumps(envelope, sort_keys=True))
    else:
        _line(f"{cmd}: {status}", args=args, color="green" if ok else "red")
        if root:
            _line(f"  root: {root}", args=args, color="dim")
    return envelope


class _Progress:
    """A context manager bracketing one long-running step with a short
    note on stderr -- silent entirely under `--json`, where stdout is a
    machine's only channel and stderr stays uncluttered too."""

    def __init__(self, message: str, *, args=None, file=None):
        self.message = message
        self.args = args
        self.file = file or sys.stderr

    def __enter__(self):
        if not getattr(self.args, "json", False):
            print(f"... {self.message}", end="", file=self.file, flush=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        if not getattr(self.args, "json", False):
            print(" done" if exc_type is None else " failed", file=self.file)
        return False
