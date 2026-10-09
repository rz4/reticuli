"""`_cli/handlers.py`: the `init` and `run` verb handlers (`spec/layers.md`'s
surface layer) -- session setup, a traced run, and a named producer's
credential preflight (`checks/handlers_check.py`, this module's definition).

`init` marks a workspace as a session: it creates the store directory
`reticuli.hooks.event` looks for (`reticuli.kernel.STORE`), so the agents
and surface layers agree on what "a session has started here" means, and --
unless `no_agent` -- wires the coding-agent handshake
(`reticuli.hooks.install`). It is idempotent: a workspace already marked is
reported as such, never recreated.

`run` drives one command inside a workspace and returns the child's exit
code unchanged, so a session (human or agent) can use the call as a
predicate (`if handlers.run(cmd, ws) == 0: ...`) while the run still lands
in the session's trace the same way a hook-reported Bash tool call would
(`reticuli.authoring.TRACE`). A `cmd` naming one of the built-in
`_PRODUCERS` is expanded to that producer's invocation (`_expand_producer`)
and preflighted against its declared credential (`_ensure`) *before*
anything runs -- a producer that would fail for a missing key fails for
free, not after spending a call. `_PRODUCER_PASSTHROUGH` lists the
environment variables a named producer is always handed past the scrub,
the same road `kernel.rebuild`'s `producer_env` describes
(`spec/kernel-api.md`).

Built from `reticuli.kernel`, `reticuli._util`, `reticuli.hooks`, and
`reticuli.authoring` -- the agents layer and below (`spec/layers.md`);
never a kernel private. Stdlib only.
"""
import os
import platform
import subprocess
import time

from reticuli import _util, hooks, kernel
from reticuli.authoring import TRACE

# -- Named producers: a short name expands to an invocation and the
# credential it needs before it may spend. Any other `cmd` passes through
# unchanged, needing no credential. ----------------------------------------

_PRODUCERS = {
    "codex": {
        "cmd": "codex exec --full-auto --sandbox workspace-write",
        "credential": "OPENAI_API_KEY",
    },
    "claude": {
        "cmd": "claude --print --dangerously-skip-permissions",
        "credential": "ANTHROPIC_API_KEY",
    },
}

# Variables a named producer is always handed past the environment scrub,
# alongside its own declared credential (`spec/kernel-api.md`'s
# `producer_env`): where to reach it, and the two spending ceilings a
# session may have set for it.
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')


def _expand_producer(cmd: str):
    """`cmd` as an actual shell command, paired with the credential it
    needs before it may spend, if any: a name in `_PRODUCERS` expands to
    that producer's invocation and declared credential; any other string
    passes through unchanged, needing no credential.
    """
    spec = _PRODUCERS.get(cmd)
    if spec is None:
        return cmd, None
    return spec["cmd"], spec.get("credential")


def _ensure(var: str) -> None:
    """Refuse before spending: raise unless credential `var` is set in the
    environment -- a named producer's preflight."""
    if not os.environ.get(var):
        raise kernel.ClaimError(f"producer credential {var!r} is not set")


def _producer_env(credential: str) -> dict:
    """The environment handed to a named producer's subprocess: `PATH`
    plus its declared credential and whatever `_PRODUCER_PASSTHROUGH`
    names -- the only road an inherited variable may travel.
    """
    env = {"PATH": os.environ.get("PATH", "")}
    for var in (credential,) + _PRODUCER_PASSTHROUGH:
        if var and var in os.environ:
            env[var] = os.environ[var]
    return env


def _version_line() -> str:
    """One line identifying this tool and its Python runtime, the shape
    `spec/record.md`'s `tool` member carries."""
    return f"reticuli ({platform.python_implementation()} {platform.python_version()})"


def _scan_workspace(ws: str) -> dict:
    """What already exists at `ws`: whether its store is marked and
    whether a session trace has been recorded -- so `init` can stay
    idempotent and report what it found rather than silently overwriting
    it.
    """
    return {
        "store": os.path.isdir(os.path.join(ws, kernel.STORE)),
        "trace": os.path.isfile(os.path.join(ws, TRACE)),
    }


def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a session: create its store directory so
    `reticuli.hooks.event` recognizes it, and -- unless `no_agent` -- wire
    the coding-agent handshake (`reticuli.hooks.install`). Idempotent: a
    workspace already marked is reported, not recreated.
    """
    before = _scan_workspace(ws)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)

    wired = None
    if not no_agent:
        wired = hooks.install(ws)

    return {
        "path": ws,
        "status": "already a session" if before["store"] else "initialized",
        "tool": _version_line(),
        "hooks": wired,
    }


def run(cmd: str, ws: str) -> int:
    """Run `cmd` inside workspace `ws`, record it to the session's trace
    the way a hook-reported Bash tool call would, and return the child's
    exit code unchanged -- a session can use the call as a predicate. A
    `cmd` naming a built-in producer (`_PRODUCERS`) is expanded and its
    credential preflighted (`_ensure`) before anything runs, and the
    producer's subprocess gets a scrubbed environment (`_producer_env`);
    any other `cmd` runs with the caller's own environment.
    """
    expanded, credential = _expand_producer(cmd)

    env = os.environ.copy()
    if credential:
        _ensure(credential)
        env = _producer_env(credential)

    _util.trace_append(os.path.join(ws, TRACE),
                        {"event": "bash", "cmd": cmd, "ts": time.time()})

    proc = subprocess.run(expanded, shell=True, cwd=ws, env=env)
    return proc.returncode
