"""The CLI's terminal boundary: the `--json` envelope and the one-voice line.

Every verb ends through `_finish`: under `--json` it prints one envelope
object (`command`/`ok`/`status`/`root`/`data`) and nothing else; in text
mode it prints a short human line, or the one-voice error line if the verb
failed. `_err`/`_warn_block` write that same voice ("ret: <verb>: <fact>")
to stderr regardless of `--json`, since a machine reader parses stdout and
a human reads stderr. `_confirm` is the one place a verb may ask before
acting, and it always refuses rather than block when there is no human to
ask. `_Progress` is the stderr step narrator a long verb (`rebuild`,
`audit`, `crosscheck`) reports through. `_line`/`_rel` are the small display
helpers every verb's text-mode rendering builds on.

Stdlib only.
"""
import json
import os
import sys

ENVELOPE_KEYS = ("command", "ok", "status", "root", "data")


def _rel(path: str) -> str:
    """`path` relative to the current directory, or unchanged if that fails
    (different drive, or no such relation)."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def _line(args, text: str) -> None:
    """One line of human-readable stdout; silent under `--json`."""
    if getattr(args, "json", False):
        return
    print(text)


def _err(command: str, fact: str) -> None:
    """The one-voice error line, always on stderr: `ret: <command>: <fact>`."""
    print(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(command: str, lines) -> None:
    """Several one-voice lines on stderr, one per entry in `lines`."""
    for line in lines:
        print(f"ret: {command}: {line}", file=sys.stderr)


def _confirm(args, prompt: str) -> bool:
    """Ask the human to confirm `prompt`; `--json` or no tty refuses outright
    rather than block waiting on input that will never come."""
    if getattr(args, "json", False) or not sys.stdin.isatty():
        return False
    try:
        reply = input(f"{prompt} [y/N] ")
    except EOFError:
        return False
    return reply.strip().lower() in ("y", "yes")


def _finish(command: str, data: dict, ok: bool, status: str, args,
            error: str = None) -> None:
    """Close out `command`: one JSON envelope under `--json`, one line else.

    `data` carries the verb's own result shape; `root`, when present in
    `data`, is promoted to the envelope's own top-level field so a reader
    never has to dig for the one value every claim-shaped result has.
    """
    root = data.get("root") if isinstance(data, dict) else None
    if getattr(args, "json", False):
        envelope = {"command": command, "ok": ok, "status": status,
                    "root": root, "data": data}
        print(json.dumps(envelope, sort_keys=True))
        return
    if not ok and error is not None:
        _err(command, error)
        return
    label = "ok" if ok else "failed"
    if root:
        print(f"{command}: {label} ({status}) root={root[:8]}")
    else:
        print(f"{command}: {label} ({status})")


class _Progress:
    """A stderr step narrator for a long-running verb.

        with _Progress(args, "rebuild") as p:
            p.step("furnishing the room")
            ...

    Silent under `--json` and under plain (non `--verbose`) text mode, so a
    machine reader's stdout never carries narration and a casual run stays
    quiet.
    """

    def __init__(self, args, command: str):
        self._command = command
        self._quiet = getattr(args, "json", False) or not getattr(
            args, "verbose", False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def step(self, text: str) -> None:
        if self._quiet:
            return
        print(f"ret: {self._command}: {text}", file=sys.stderr)
