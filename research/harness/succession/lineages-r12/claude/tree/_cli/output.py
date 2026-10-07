"""The CLI's output contract: the `--json` envelope and the one-voice
error line.

Every verb finishes through `_finish`, which emits exactly one shape:
`--json` prints the five-field envelope (`command`, `ok`, `status`,
`root`, `data`) and nothing else on stdout, so a script parsing that
output never has to skip human prose; without `--json` it prints a short
colored line instead, honoring `args.color` (`always` / `never` /
`auto`, the last deciding by `sys.stdout.isatty()`). Every refusal speaks
in one voice through `_err`: `ret: <verb>: <fact>`, on stderr, no
traceback. `_Progress`, `_line`, `_warn_block`, `_confirm`, and `_rel`
are the small presentation helpers the verbs share to stay inside that
contract.

Stdlib only.
"""
import json
import sys

from .. import render


def _use_color(args) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _rel(path: str) -> str:
    """`path` relative to the current directory, for display -- the
    absolute form a kernel call wants is not what a human wants to read.
    """
    import os
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def _line(text: str, args, color: str = None) -> None:
    """Print one line of human-facing output, honoring `--color`."""
    if color and _use_color(args):
        text = render.paint(text, color)
    print(text)


def _warn_block(lines, args) -> None:
    """A multi-line, one-warning-per-line block on stderr."""
    for line in lines:
        text = f"warning: {line}"
        if _use_color(args):
            text = render.paint(text, "yellow")
        print(text, file=sys.stderr)


def _err(cmd: str, fact: str) -> None:
    """The one-voice error line: `ret: <verb>: <fact>`, on stderr."""
    print(f"ret: {cmd}: {fact}", file=sys.stderr)


def _confirm(prompt: str, default: bool = False) -> bool:
    """A y/n prompt on stdin; non-interactive input answers `default`
    rather than blocking -- a script piping into a verb must never hang.
    """
    if not sys.stdin.isatty():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def _finish(cmd: str, data: dict, ok: bool, status: str, args, root: str) -> dict:
    """Build and emit the output envelope; also returns it, so a caller
    embedding this tool can read the verdict without reparsing stdout.
    """
    env = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}
    if getattr(args, "json", False):
        print(json.dumps(env, sort_keys=True))
    else:
        _line(f"{cmd}: {status}", args, "green" if ok else "red")
        if getattr(args, "verbose", False) and data:
            for key in sorted(data):
                print(f"  {key}: {data[key]}")
    return env


class _Progress:
    """A step counter for a multi-step verb (`rebuild`, `audit`).

    Silent under `--json`, so the envelope stays the only thing on
    stdout a script sees; otherwise prints one dim `[n/total] text` line
    per step.
    """

    def __init__(self, args, total: int = None):
        self._args = args
        self._total = total
        self._n = 0

    def step(self, text: str) -> None:
        self._n += 1
        if getattr(self._args, "json", False):
            return
        prefix = f"[{self._n}/{self._total}]" if self._total else f"[{self._n}]"
        _line(f"{prefix} {text}", self._args, "dim")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False
