"""reticuli._cli.handlers -- session setup, traced run, producer dispatch
(spec/layers.md: surface).

`init` marks a fresh workspace -- its `.reticuli/` store, and -- unless
`no_agent` -- the coding-agent handshake wired into it (`hooks.install`)
-- so a session has somewhere to leave its trace before anything is
sealed. `run` executes one shell command inside a workspace, appends the
same kind of trace event the agent handshake writes for a `Bash` tool
call (`hooks.TRACE`), and returns the child's exit code unchanged -- never
swallowed, so a session (human or scripted) can use it as a predicate.

A **producer** is the command a rebuild hands its generated outputs to.
`_PRODUCERS` names the shorthands this CLI understands, each with the
credential it needs; `_expand_producer` turns a shorthand (or an
already-literal command) into the command and environment `kernel.rebuild`
actually uses, and `_ensure` preflights the named credential -- refusing
before anything is spent, rather than after a producer fails partway
through a paid call. `_PRODUCER_PASSTHROUGH` names the host environment
variables a rebuild may hand a producer past the scrub, when present --
the only road an inherited credential or cost cap travels.
"""
import json
import os
import subprocess
import sys
import time

from reticuli import kernel, hooks

_VERSION = "2.2"

_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

_PRODUCERS = {
    "codex": {"command": "codex exec --full-auto", "credential": "OPENAI_API_KEY"},
    "claude": {"command": "claude --print --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
}


# -- producer dispatch: shorthand -> command, credential preflighted -------

def _ensure(name: str) -> None:
    """Refuse before spending: a named producer's credential must already
    be set in the environment. A name outside `_PRODUCERS` is a literal
    command, with no credential of its own to check."""
    spec = _PRODUCERS.get(name)
    if spec is None:
        return
    credential = spec.get("credential")
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(f"producer {name!r} needs {credential} set in the environment")


def _expand_producer(producer: str):
    """`(command, env)` for `producer`: a named shorthand's command, its
    credential preflighted (`_ensure`) first, plus whichever of
    `_PRODUCER_PASSTHROUGH` the host has set; anything not in
    `_PRODUCERS` is already a literal command, passed through with no
    extra environment beyond the passthrough."""
    env = {name: os.environ[name] for name in _PRODUCER_PASSTHROUGH if name in os.environ}
    spec = _PRODUCERS.get(producer)
    if spec is None:
        return producer, env
    _ensure(producer)
    credential = spec.get("credential")
    if credential and credential in os.environ:
        env[credential] = os.environ[credential]
    return spec["command"], env


# -- reading what a workspace looks like right now --------------------------

def _scan_workspace(ws: str) -> dict:
    """What `ws` looks like right now: whether it is marked (`.reticuli/`
    present) and whether a session trace exists, and how many events it
    holds -- the one read `init` and `run` share before they act."""
    marked = os.path.isdir(os.path.join(ws, kernel.STORE))
    trace_path = os.path.join(ws, hooks.TRACE)
    events = 0
    if os.path.isfile(trace_path):
        with open(trace_path, "r", encoding="utf-8") as f:
            events = sum(1 for line in f if line.strip())
    return {"marked": marked, "trace_present": os.path.isfile(trace_path), "events": events}


def _version_line() -> str:
    """One line identifying this build, for `--version`."""
    return f"reticuli {_VERSION} (python {sys.version.split()[0]})"


# -- init / run ---------------------------------------------------------

def init(workspace: str, no_agent: bool = False) -> dict:
    """Mark `workspace` as a session: create its `.reticuli/` store, and
    -- unless `no_agent` -- wire the coding-agent handshake into it
    (`hooks.install`), so a session's trace starts filling without a
    separate step."""
    ws = os.path.abspath(workspace)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    agent = None if no_agent else hooks.install(ws)
    return {"ok": True, "workspace": ws, "agent": agent}


def run(command: str, workspace: str) -> int:
    """Run `command` as a shell command inside `workspace`, trace it into
    the session's draft trace -- the same event shape `hooks.event` writes
    for a `Bash` tool call -- and return the child's exit code unchanged,
    so a session can use it as a predicate without reticuli swallowing the
    result."""
    ws = os.path.abspath(workspace)
    done = subprocess.run(command, shell=True, cwd=ws)

    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        path = os.path.join(ws, hooks.TRACE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "bash", "cmd": command, "ts": time.time()},
                                sort_keys=True))
            f.write("\n")

    return done.returncode
