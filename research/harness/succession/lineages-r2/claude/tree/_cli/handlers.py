"""reticuli._cli.handlers: session setup, traced run, producer preflight
(spec/layers.md, surface layer).

`init` marks a directory as a reticuli session (a `.reticuli/` store) and,
unless `no_agent`, wires the coding-agent handshake (`hooks.install`) and
hands off to a named producer's own interactive agent session. `run`
executes one command inside a session, appending it to the session's own
draft trace (`hooks.TRACE` -- the same file an agent's own Bash calls land
in) so a human or scripted invocation reads back the same way; the child's
exit code is returned unchanged, so a session's own driver can use `run` as
a predicate without translation. A named producer's credential is
preflighted (`_ensure`) before an agent session that would spend against it
is launched, rather than failing mid-session.

Stdlib only.
"""
import json
import os
import shlex
import shutil
import subprocess
import time

from .. import _util, hooks, kernel

STORE = kernel.STORE

_ENV_PRODUCER = "RETICULI_PRODUCER"

# named producers: producer name -> its own agent CLI, and the credential
# (an environment variable) it needs set before it can spend
_PRODUCERS = {
    "codex": {"argv": ["codex", "exec"], "credential": None},
    "claude": {"argv": ["claude", "-p", "--dangerously-skip-permissions"], "credential": None},
    "openai": {"argv": ["codex", "exec"], "credential": "OPENAI_API_KEY"},
}

# environment variables threaded from the caller's own environment into a
# spawned producer -- its endpoint and spend limits, nothing else of the
# caller's environment crosses that boundary uninvited
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

_BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


def _expand_producer(producer: str) -> list:
    """`producer`'s argv: a name declared in `_PRODUCERS` expands to its own
    command, anything else is a literal shell command split the normal
    way."""
    spec = _PRODUCERS.get(producer)
    if spec is not None:
        return list(spec["argv"])
    return shlex.split(producer)


def _ensure(producer: str) -> None:
    """Preflight `producer`'s credential before an agent session spends
    against it: refuse (`kernel.ClaimError`) early rather than mid-session,
    for a missing declared credential or a CLI that is not on `PATH`."""
    spec = _PRODUCERS.get(producer)
    credential = spec.get("credential") if spec else None
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(
            f"producer {producer!r} needs {credential} set before it can spend")
    argv = _expand_producer(producer)
    exe = argv[0] if argv else producer
    if shutil.which(exe) is None:
        raise kernel.ClaimError(f"producer {producer!r} is not on PATH: {exe!r} missing")


def _producer_env() -> dict:
    """The subset of the caller's own environment threaded into a spawned
    producer (`_PRODUCER_PASSTHROUGH`), plus enough of the ordinary
    environment (`_BASE_ENV`) for its own CLI to run at all."""
    env = {k: os.environ[k] for k in _BASE_ENV if k in os.environ}
    env.update({k: os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ})
    return env


def _launch_agent(producer: str, ws: str) -> int:
    """Hand off to `producer`'s own interactive agent session, foregrounded
    in session `ws`. Returns the session's exit code unchanged."""
    argv = _expand_producer(producer)
    proc = subprocess.run(argv, cwd=ws, env=_producer_env())
    return proc.returncode


def _scan_workspace(ws: str) -> dict:
    """What already exists at `ws`: whether it is a session at all, and
    which sealed claims its store already holds -- `init`'s idempotence
    check, and a session status line's raw material."""
    sealed_dir = os.path.join(ws, STORE, "sealed")
    claims = sorted(os.listdir(sealed_dir)) if os.path.isdir(sealed_dir) else []
    return {"marked": os.path.isdir(os.path.join(ws, STORE)), "claims": claims}


def _version_line() -> str:
    """The one line a version verb prints: namespace and wire format, the
    two facts that decide whether two sessions can talk to each other."""
    return f"reticuli {kernel.NAMESPACE}/{kernel.FORMAT}"


def init(ws: str, producer: str = None, no_agent: bool = False) -> dict:
    """Mark `ws` as a reticuli session: create its store, and unless
    `no_agent`, wire the coding-agent handshake and hand off to a named
    producer's own agent session. A session meant only to hold sealed
    claims by hand -- no agent will ever write into its trace -- passes
    `no_agent` to skip the hook and the producer preflight both."""
    os.makedirs(os.path.join(ws, STORE), exist_ok=True)
    if no_agent:
        return {"status": "initialized", "path": ws, "agent": False}

    hooks.install(ws)
    producer = producer or os.environ.get(_ENV_PRODUCER)
    result = {"status": "initialized", "path": ws, "agent": True}
    if producer:
        _ensure(producer)
        result["producer"] = producer
        result["returncode"] = _launch_agent(producer, ws)
    return result


def run(cmd: str, ws: str) -> int:
    """Run `cmd` inside session `ws`, traced into its own draft trace
    (`hooks.TRACE`) the same way an agent's own Bash calls are traced --
    so a human or scripted `run` reads back beside them. The child's exit
    code is returned unchanged, so a session's own driver can use `run` as
    a predicate (a test suite, a gate) without translation."""
    proc = subprocess.run(["/bin/sh", "-c", cmd], cwd=ws)
    if os.path.isdir(os.path.join(ws, STORE)):
        entry = {"event": "bash", "cmd": cmd, "returncode": proc.returncode, "ts": time.time()}
        _util.locked_append(os.path.join(ws, hooks.TRACE), json.dumps(entry, sort_keys=True))
    return proc.returncode
