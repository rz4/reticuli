"""Session setup, traced run, producer preflight (`spec/layers.md`: surface,
`_cli/handlers.py`).

`init` marks a directory as a workspace (`kernel.STORE`, `.reticuli/`) and,
unless `no_agent`, wires the coding-agent hook handshake into it
(`hooks.install`) -- the same store a session's draft trace
(`reticuli.authoring.TRACE`) is read from later. `run` executes one command
in a workspace, traced into that same session log exactly as a hook-driven
Bash tool call would be (`reticuli.hooks.event`), and returns the child's
exit code unchanged, so a session can chain it as a predicate
(`ret run check.sh && ret seal .`). A command naming a known producer in
`_PRODUCERS` is expanded to that producer's own command line and preflighted
first: a missing credential refuses before anything is spent, rather than
after a producer has already run and billed.

Stdlib only.
"""
import json
import os
import platform
import subprocess
import sys
import time

from reticuli import _util, kernel
from reticuli.authoring import TRACE
from reticuli import hooks

# -- named producers: a short name -> its own command line and the ---------
# -- credential (an environment variable) it needs before it may spend -----
_PRODUCERS = {
    "codex": {"cmd": "codex exec --full-auto --skip-git-repo-check -",
               "credential": None},
    "claude": {"cmd": "claude -p --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
    "openai": {"cmd": "openai api chat.completions.create",
               "credential": "OPENAI_API_KEY"},
}

# -- environment variables a named producer's run is handed in addition to
# -- its own credential and the base allowlist: endpoint override, a
# -- self-imposed price ceiling, a turn-count ceiling.
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

_BASE_ENV = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR')


def _ensure(name: str) -> dict:
    """Preflight a named producer's credential before spending.

    Returns its `_PRODUCERS` entry on success; raises `kernel.ClaimError`
    naming the unknown producer or the unset credential.
    """
    entry = _PRODUCERS.get(name)
    if entry is None:
        raise kernel.ClaimError(f"unknown producer {name!r}")
    credential = entry.get("credential")
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(
            f"producer {name!r} needs {credential} set; refusing before spending")
    return entry


def _expand_producer(cmd: str) -> str:
    """`cmd` as a shell command: a name in `_PRODUCERS` is preflighted via
    `_ensure` and expanded to its own command line; anything else -- an
    ordinary shell command -- runs unchanged."""
    if cmd not in _PRODUCERS:
        return cmd
    return _ensure(cmd)["cmd"]


def _producer_env(name: str) -> dict:
    """A scrubbed environment for a named producer's subprocess: a small
    host allowlist, its own credential (if any), and the passthrough
    knobs in `_PRODUCER_PASSTHROUGH` -- never the caller's full, unscrubbed
    environment, which may carry secrets the producer has no claim to."""
    env = {k: os.environ[k] for k in _BASE_ENV if k in os.environ}
    credential = _PRODUCERS[name].get("credential")
    if credential and credential in os.environ:
        env[credential] = os.environ[credential]
    for key in _PRODUCER_PASSTHROUGH:
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _scan_workspace(ws: str) -> dict:
    """What `init` finds already there: whether `ws` exists, whether it is
    already marked as a workspace (`kernel.STORE` present), and how many
    events its session trace already carries."""
    existed = os.path.isdir(ws)
    marked = existed and os.path.isdir(os.path.join(ws, kernel.STORE))
    events = 0
    trace_path = os.path.join(ws, TRACE)
    if os.path.isfile(trace_path):
        with open(trace_path, encoding="utf-8") as f:
            events = sum(1 for line in f if line.strip())
    return {"existed": existed, "marked": marked, "events": events}


def _version_line() -> str:
    """One banner line identifying the interpreter this session runs
    under -- diagnostic only, carried into a fresh session's trace by
    `init`, never read back by anything that decides acceptance."""
    return (f"reticuli on {platform.python_implementation()} "
            f"{platform.python_version()} ({sys.platform})")


def _trace(ws: str, fields: dict) -> None:
    """Append one event to `ws`'s session trace, in the same shape a
    coding-agent hook would write (`reticuli.hooks._append`)."""
    entry = {"ts": time.time(), **fields}
    path = os.path.join(ws, TRACE)
    _util.locked_append(path, json.dumps(entry, sort_keys=True))


# -- init ---------------------------------------------------------------------

def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a workspace: create its store (`kernel.STORE`) and,
    unless `no_agent`, wire the coding-agent hook handshake into it
    (`hooks.install`). Idempotent -- re-running it on an already-marked
    workspace changes nothing it did not already have."""
    before = _scan_workspace(ws)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)

    wired = None
    if not no_agent:
        wired = hooks.install(ws)

    _trace(ws, {"event": "session", "version": _version_line()})
    return {"workspace": ws, "resumed": before["marked"], "wired": wired}


# -- run ------------------------------------------------------------------

def run(cmd: str, ws: str) -> int:
    """Run `cmd` in `ws`, traced into its session log, and return the
    child's exit code unchanged (`spec/layers.md`: CLI verb `run`,
    unchanged from v1).

    A `cmd` naming a known producer in `_PRODUCERS` is preflighted and
    expanded to that producer's own command line, and runs under a
    scrubbed environment (`_producer_env`); any other `cmd` is an ordinary
    shell command and runs with the caller's own environment, unchanged.
    """
    named = cmd in _PRODUCERS
    expanded = _expand_producer(cmd)
    env = _producer_env(cmd) if named else dict(os.environ)

    os.makedirs(ws, exist_ok=True)
    result = subprocess.run(expanded, shell=True, cwd=ws, env=env)

    _trace(ws, {"event": "bash", "cmd": cmd})
    return result.returncode
