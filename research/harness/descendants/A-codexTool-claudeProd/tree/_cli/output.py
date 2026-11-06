"""The channel contract: who speaks where, and in what words.

Three rules, and they are the whole module.

**The silence rule.**  A passing check says nothing — the exit code is the
answer.  Makers print the unknowable (the root a rebuild landed on, the path
a file went to); views speak, because being read is their whole job.

**One voice for every refusal.**  Every diagnostic is `ret: <verb>: <fact>`
on **stderr**, class-first, followed where useful by a `hint:` line.  stdout
carries results, so a caller piping `--json` into a parser never finds a
diagnostic in the stream.

**The envelope is stable.**  Under `--json` every verb answers with exactly
`{command, ok, status, root, data}` — five top-level fields, the verb echoed
back, and the verb's own detail underneath `data`.  It holds on the FAILURE
path too: a refusal still speaks the envelope with `ok: false` and the fact
under `data.error`, so `ret <verb> --json | jq` never chokes on an empty
stdout.  The exit-2 seam is the deliberate exception — an invalid invocation
is refused before a verb runs, so it stays a plain stderr line with no
envelope at all.
"""
import json
import os
import sys


def _wants_color(args) -> bool:
    """Colour as `ls` does it: auto by tty, always/never overriding.

    Information never lives only in a hue, so every label word returns
    wherever colour is off.
    """
    choice = getattr(args, "color", None) or "auto"
    if choice == "auto":
        choice = os.environ.get("RETICULI_COLOR") or "auto"
    if choice == "always":
        return True
    if choice == "never":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _rel(path) -> str:
    """A path as a reader would type it, when that is shorter."""
    if not path:
        return "-"
    try:
        relative = os.path.relpath(str(path))
    except ValueError:
        return str(path)
    return relative if len(relative) <= len(str(path)) else str(path)


def _line(label: str, value, width: int = 12) -> str:
    """One `label  value` line of a view."""
    return f"{str(label):<{width}} {'' if value is None else value}".rstrip()


def _err(command: str, fact, hint: str = None) -> None:
    """The one-voice refusal, on stderr, class-first."""
    print(f"ret: {command}: {fact}", file=sys.stderr)
    if hint:
        print(f"  hint: {hint}", file=sys.stderr)


def _warn_block(command: str, lines) -> None:
    """Several facts about one refusal, still in one voice."""
    for index, line in enumerate(lines or []):
        if index == 0:
            print(f"ret: {command}: {line}", file=sys.stderr)
        else:
            print(f"  {line}", file=sys.stderr)


def _confirm(question: str, assume: bool = False) -> bool:
    """Ask, unless there is nobody to ask."""
    if assume or not sys.stdin.isatty():
        return assume
    answer = input(f"{question} [y/N] ").strip().lower()
    return answer in ("y", "yes")


class _Progress:
    """A quiet progress channel: stderr, and only when asked for.

    Progress is not a result, so it never touches stdout; and a run nobody
    is watching should not pay for it.
    """

    def __init__(self, label: str, args=None):
        self.label = label
        self.show = bool(getattr(args, "progress", False))

    def __enter__(self):
        if self.show:
            print(f"{self.label}...", file=sys.stderr)
        return self

    def step(self, note: str) -> None:
        if self.show:
            print(f"  {note}", file=sys.stderr)

    def __exit__(self, kind, value, trace):
        return False


def envelope(command: str, data, ok: bool, status: str, root=None) -> dict:
    """The five stable fields, and nothing else."""
    if root is None and isinstance(data, dict):
        root = data.get("root")
    return {"command": command, "ok": bool(ok), "status": status,
            "root": root, "data": data}


def _finish(command: str, data, ok: bool, status: str, args,
            renderer=None, root=None) -> int:
    """Answer in whichever register was asked for, and exit by the predicate."""
    if getattr(args, "json", False):
        print(json.dumps(envelope(command, data, ok, status, root),
                         sort_keys=True, indent=2))
    elif renderer is not None:
        renderer(data, args, status)
    return 0 if ok else 1


def _refusal(command: str, fact, args, hint: str = None) -> int:
    """A refusal, in whichever register the caller asked for."""
    if getattr(args, "json", False):
        print(json.dumps(
            envelope(command, {"error": str(fact)}, False, "error", None),
            sort_keys=True, indent=2))
        return 1
    _err(command, fact, hint)
    return 1
