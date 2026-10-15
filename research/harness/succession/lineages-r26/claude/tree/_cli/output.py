"""The CLI's output contract -- see `checks/base_check.py`.

Every verb ends by calling `_finish`, which prints the documented five-key
`--json` envelope (`command`, `ok`, `status`, `root`, `data`) or, otherwise,
a human line built by `_line`. Every refusal speaks with the one voice
`_err` prints -- `ret: <verb>: <fact>`, always to stderr, regardless of
`--json`, so a script watching stderr never has to learn two error
grammars. Stdlib only.
"""
import json
import os
import sys

_COLOR = {"ok": "\033[32m", "warn": "\033[33m", "err": "\033[31m", "reset": "\033[0m"}


def _use_color(args) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, kind: str, args) -> str:
    if not _use_color(args):
        return text
    return f"{_COLOR.get(kind, '')}{text}{_COLOR['reset']}"


def _rel(path: str, base: str) -> str:
    """`path` relative to `base`, for display -- falls back to `path`
    itself when the two share no common root (e.g. across drives)."""
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _line(command: str, data, ok: bool, status: str, args) -> str:
    """One human-readable line for a finished verb."""
    root = data.get("root") if isinstance(data, dict) else None
    pieces = [command, "ok" if ok else "FAIL", status]
    if root:
        pieces.append(str(root)[:12])
    return " ".join(pieces)


def _err(command: str, fact: str) -> None:
    """The one-voice refusal line: `ret: <verb>: <fact>`, to stderr."""
    print(f"ret: {command}: {fact}", file=sys.stderr)


def _warn_block(command: str, lines) -> None:
    """A multi-line warning in the same voice `_err` uses for a refusal,
    so a warning reads as a family member of an error, not a different
    grammar a script must also learn."""
    if isinstance(lines, str):
        lines = [lines]
    for line in lines:
        print(f"ret: {command}: warning: {line}", file=sys.stderr)


def _confirm(prompt: str, default: bool = False) -> bool:
    """A durable human act: ask on stdin, never assume consent."""
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        reply = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not reply:
        return default
    return reply in ("y", "yes")


class _Progress:
    """A status line for a long-running verb.

    Silent unless `args.verbose`, so a script consuming `--json` or a
    plain pipe never sees interleaved chatter.
    """

    def __init__(self, label: str, args=None):
        self.label = label
        self._active = bool(getattr(args, "verbose", False)) if args is not None else False

    def __enter__(self):
        if self._active:
            print(f"... {self.label}", file=sys.stderr)
        return self

    def update(self, text: str) -> None:
        if self._active:
            print(f"... {self.label}: {text}", file=sys.stderr)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _finish(command: str, data, ok: bool, status: str, args, root=None) -> dict:
    """Print the documented envelope and return it.

    `--json` prints the five-key envelope verbatim; otherwise a human
    line from `_line`. `root` may be given explicitly for a verb that
    computed one but did not carry it in `data`; absent that, it is read
    from `data["root"]`.
    """
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": ok, "status": status, "root": root, "data": data}
    if getattr(args, "json", False):
        print(json.dumps(envelope))
    else:
        print(_paint(_line(command, data, ok, status, args), "ok" if ok else "err", args))
    return envelope
