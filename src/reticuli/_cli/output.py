"""ret command line — the output layer: the output contract — silence, -v, the --json envelope, errors, progress."""
from __future__ import annotations

import json
import os
import sys
import time

from ..render import duration, paint

# -- the output contract (docs/cli-style.md): silence | -v | --json ---------


def _finish(command: str, r: dict, ok: bool, status: str, args,
            rich, terse=None) -> None:
    """One output contract for every verb: the default is `terse` — or, for
    a check succeeding, SILENCE (terse=None prints nothing: the exit code is
    the answer). `-v` is `rich` (the explanatory fact sheets), `--json` the
    envelope. The envelope's stable fields are command/ok/status/root/data;
    everything verb-specific lives under data, because the durable exchange
    object is the claim/record format, not CLI presentation JSON — the
    envelope is the only parse-stable output."""
    if getattr(args, "json", False):
        print(json.dumps({"command": command, "ok": bool(ok), "status": status,
                          "root": r.get("root"), "data": r},
                         indent=2, sort_keys=True))
    elif getattr(args, "verbose", False):
        rich(r)
    elif terse is not None:
        terse(r)




def _line(*parts) -> None:
    print("  ".join(str(p) for p in parts if p not in (None, "")))




def _warn_block(warns) -> None:
    """Honest-partial pack findings, on stderr — the packed root stays on
    stdout. A pack succeeds WITH warnings: the block says what could not be
    established, it does not withhold the claim (the cold re-earn already did
    the deciding). --json carries the same findings under data instead."""
    print("  warnings", file=sys.stderr)
    for w in warns:
        print(f"    {w['detail']}", file=sys.stderr)




def _err(verb: str, fact: str, hint: str | None = None,
         detail: list | None = None) -> None:
    """A failure, git-shaped: `ret: <verb>: <fact>`, optional indented
    detail lines, optional `hint:` — all on stderr, per the style contract."""
    print(f"ret: {verb}: {fact}", file=sys.stderr)
    for line in detail or []:
        print(f"  {line}", file=sys.stderr)
    if hint:
        print(paint(f"hint: {hint}", "hint", stderr=True), file=sys.stderr)




def _confirm(line: str) -> None:
    """A one-line success note for the silent verification verbs — on stderr,
    and only on an interactive terminal.

    The silence rule stands where it matters: piped, redirected, or in CI,
    stderr is not a tty, nothing prints, and the exit code is the whole answer,
    so `ret verify … && …` and `ret audit … | jq` are untouched. stdout is never
    written, so `--json` is untouched too. What changes is only the interactive
    case a newcomer hits: running the flagship check and getting a blank line,
    unable to tell 'passed' from 'did nothing'. Same tty gate the progress
    spinner uses."""
    try:
        if sys.stderr.isatty():
            print(paint(line, "pass", stderr=True), file=sys.stderr)
    except (AttributeError, ValueError):
        pass




def _rel(path: str) -> str:
    """git's path rule: relative when under the current directory."""
    absd = os.path.abspath(path)
    cwd = os.getcwd()
    if absd == cwd:
        return "."
    if absd.startswith(cwd + os.sep):
        return os.path.relpath(absd, cwd)
    return absd




class _Progress:
    """Long work announces itself on a terminal and cleans up after: a
    stderr line rewritten in place, erased on completion — so the end state
    still honors the silence rule. Pipes and CI never see it."""

    def __init__(self, label: str):
        self.label = label
        self.live = False
        try:
            self.live = sys.stderr.isatty()
        except (AttributeError, ValueError):
            self.live = False

    def __enter__(self):
        if self.live:
            import threading
            self.stop = threading.Event()
            self.t0 = time.monotonic()

            def tick():
                while not self.stop.wait(1.0):
                    line = f"{self.label} {duration(time.monotonic() - self.t0)}"
                    print(f"\r{paint(line, 'meta', stderr=True)}\x1b[K",
                          end="", file=sys.stderr, flush=True)
            self.thread = threading.Thread(target=tick, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        if self.live:
            self.stop.set()
            self.thread.join(timeout=2)
            print("\r\x1b[K", end="", file=sys.stderr, flush=True)
        return False
