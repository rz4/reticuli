"""The channel contract.

Three levels, one voice. TERSE by default -- a passing check says nothing,
because the exit code is the answer; EXPLANATORY under -v; and a stable
machine envelope under --json. Every diagnostic goes to stderr in one shape,
`ret: <verb>: <fact>`, whichever layer raised it, so a reader never has to
learn which part of the tool is speaking.
"""
import json
import os
import sys

#: The five fields of the machine envelope. Automation switches on these.
ENVELOPE = ("command", "ok", "status", "root", "data")


def _rel(path) -> str:
    """A path as a reader will recognise it: relative where that is shorter."""
    if not path:
        return "-"
    try:
        here = os.path.relpath(str(path))
    except ValueError:
        return str(path)
    return here if len(here) <= len(str(path)) else str(path)


def _line(text: str = "") -> None:
    print(text)


def _err(command: str, fact: str, hint: str | None = None) -> None:
    """One voice for every refusal: `ret: <verb>: <fact>`, on stderr."""
    print(f"ret: {command}: {fact}", file=sys.stderr)
    if hint:
        print(f"hint: {hint}", file=sys.stderr)


def _warn_block(command: str, lines) -> None:
    """Several facts about one refusal, still on stderr, still one voice."""
    for index, line in enumerate(lines or []):
        prefix = f"ret: {command}: " if index == 0 else "    "
        print(prefix + str(line), file=sys.stderr)


def _color(args) -> bool:
    """Colour as `ls` does it: auto by tty, always/never overriding."""
    choice = getattr(args, "color", None) or os.environ.get("RETICULI_COLOR") \
        or "auto"
    if os.environ.get("RETICULI_COLOR") in ("always", "never"):
        if getattr(args, "color", None) in ("always", "never"):
            choice = args.color
        else:
            choice = os.environ["RETICULI_COLOR"]
    if choice == "always":
        return True
    if choice == "never":
        return False
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _finish(command: str, data, ok: bool, status: str, args,
            root=None) -> int:
    """Close a verb: speak the envelope under --json, and exit by predicate."""
    payload = data if isinstance(data, dict) else {"result": data}
    if getattr(args, "json", False):
        envelope = {"command": command, "ok": bool(ok), "status": status,
                    "root": root if root is not None
                    else payload.get("root"),
                    "data": payload}
        print(json.dumps(envelope, sort_keys=True, default=str))
    return 0 if ok else 1


def _refuse(command: str, fact: str, args, hint: str | None = None) -> int:
    """A refusal that still speaks the envelope under --json.

    `ret <verb> --json | jq` must never choke on the first "is this a claim?"
    refusal, so the fact lands under data.error on STDOUT and stderr stays
    empty. Without --json it is the ordinary one-voice stderr line.
    """
    if getattr(args, "json", False):
        envelope = {"command": command, "ok": False, "status": "error",
                    "root": None, "data": {"error": fact}}
        print(json.dumps(envelope, sort_keys=True))
        return 1
    _err(command, fact, hint)
    return 1


class _Progress:
    """A progress note for long work -- on stderr, and only when asked.

    Verification can take minutes on a real claim, and silence then is
    indistinguishable from a hang. It stays off by default because the silence
    rule is about the RESULT channel, not about hiding work in progress.
    """

    def __init__(self, args, label: str = ""):
        self.on = bool(getattr(args, "progress", False))
        self.label = label

    def __enter__(self):
        self.say(self.label)
        return self

    def __exit__(self, kind, value, trace):
        return False

    def say(self, note: str) -> None:
        if self.on and note:
            print(f"... {note}", file=sys.stderr, flush=True)


def _confirm(question: str) -> bool:
    """Ask before something irreversible; a closed stdin means no."""
    try:
        if not sys.stdin.isatty():
            return False
        answer = input(f"{question} [y/N] ").strip().lower()
    except (OSError, EOFError, ValueError):
        return False
    return answer in ("y", "yes")
