"""The output contract: three levels, one voice, two channels.

THE SILENCE RULE. A passing check says nothing -- the exit code is the
answer. Makers print the one thing a caller could not have known (the root
they landed on). Views speak, because being read is what they are for.

THREE LEVELS. Terse by default; `-v` is the explanatory account, with hashes
spelled in full; `--json` is a stable machine envelope,
`{command, ok, status, root, data}`, and nothing else at the top level.

ONE VOICE. Every refusal is `ret: <verb>: <fact>` on stderr, from whichever
layer refused, followed where useful by a `hint:` line. Diagnostics never
land on stdout, so `ret <verb> --json | jq` is never fed a sentence.

TWO SEAMS IN THE EXIT CODES. 0 the predicate held, 1 it failed or was
refused, 2 the invocation was invalid. An exit-1 refusal still speaks the
envelope under `--json` (automation's first question is "is this a claim?",
and it must not choke). An exit-2 refusal does not: a malformed call is
answered before any verb runs, so there is nothing to put in a document.
"""
import json
import sys

from .. import render


def _rel(path) -> str:
    """A path as a reader would type it."""
    import os
    if not path:
        return "-"
    try:
        here = os.path.relpath(str(path))
    except ValueError:
        return str(path)
    return here if len(here) <= len(str(path)) else str(path)


def _line(text: str = "") -> None:
    print(text)


def _err(verb: str, fact: str) -> None:
    """The one-voice refusal line."""
    print(f"ret: {verb}: {fact}", file=sys.stderr)


def _warn_block(lines) -> None:
    """Hints and warnings: stderr, never stdout, one per line."""
    for line in lines or []:
        if line:
            print(line, file=sys.stderr)


def _confirm(question: str, assume: bool = False) -> bool:
    """Ask before something irreversible; non-interactive means no."""
    if assume:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


class _Progress:
    """A progress channel that is silent unless asked for, and on stderr
    when it is: progress is not output, and a pipe must not receive it."""

    def __init__(self, enabled: bool = False, label: str = ""):
        self.enabled = bool(enabled)
        self.label = label
        self.steps = 0

    def __enter__(self):
        if self.enabled and self.label:
            print(f"{self.label}...", file=sys.stderr)
        return self

    def __exit__(self, *_exception):
        return False

    def step(self, what: str = "") -> None:
        self.steps += 1
        if self.enabled:
            print(f"  {what}", file=sys.stderr)


def _envelope(command: str, data, ok: bool, status: str, root) -> dict:
    return {"command": command, "ok": bool(ok), "status": str(status),
            "root": root, "data": data}


def _finish(command: str, data, ok: bool, status: str, args,
            terse=None, root=None, renderer=None) -> int:
    """Emit one verb's result at whichever level was asked for."""
    if getattr(args, "json", False):
        if root is None and isinstance(data, dict):
            root = data.get("root")
        print(json.dumps(_envelope(command, data, ok, status, root),
                         sort_keys=True))
        return 0 if ok else 1
    if getattr(args, "verbose", False) and renderer is not None:
        text = renderer(data)
        if text:
            print(text)
        return 0 if ok else 1
    if terse:
        print(terse)
    return 0 if ok else 1


def _refuse(command: str, fact: str, args, hint=None) -> int:
    """A refusal that still speaks the envelope under --json."""
    if getattr(args, "json", False):
        print(json.dumps(_envelope(command, {"error": fact}, False, "error",
                                   None), sort_keys=True))
        return 1
    _err(command, fact)
    if hint:
        _warn_block([f"hint: {hint}"])
    return 1


def _paint(text: str, color: str) -> str:
    return render.paint(text, color)
