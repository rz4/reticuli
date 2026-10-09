"""Session handlers: workspace init, traced run, producer preflight.

`init` marks a directory as a session workspace -- creating it and its
`.reticuli` store -- and, unless `no_agent` withholds the handshake, wires
the coding-agent hooks into it (`reticuli.hooks.install`). `run` executes
one shell command inside a workspace and returns the child's exit code
unchanged, so a session script can chain commands and use a run's result
as its own predicate.

`_PRODUCERS` names the producers this layer knows how to preflight, each
mapped to the environment variable that carries its credential.
`_expand_producer` reads one producer's credential and whichever
`_PRODUCER_PASSTHROUGH` variables are set in this environment into the
shape a preflight or a run consults; `_ensure` is the preflight itself --
a refusal, in words, before a producer-backed run would spend anything on
a missing credential. `_scan_workspace` reports what a workspace already
holds: whether it is marked, whether a recipe is sealed there, and how
many events its session trace has recorded. `_version_line` is the one
line `--version` prints.
"""
import os
import subprocess

from reticuli import hooks, kernel

_PRODUCERS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
}

_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

_VERSION = "0.1"


def _version_line() -> str:
    """The one line `--version` prints."""
    return f"reticuli {_VERSION}"


def _expand_producer(name: str) -> dict:
    """One producer name, expanded into its credential variable (`None`
    for a name `_PRODUCERS` does not know) and whichever
    `_PRODUCER_PASSTHROUGH` variables are set in this environment."""
    passthrough = {var: os.environ[var] for var in _PRODUCER_PASSTHROUGH if var in os.environ}
    return {"name": name, "credential": _PRODUCERS.get(name), "passthrough": passthrough}


def _ensure(name: str) -> str:
    """Preflight producer `name`'s credential before a run that would
    spend: refuses, in words (`kernel.ClaimError`), an unknown producer or
    one whose credential variable is unset; returns the credential's
    value otherwise."""
    spec = _expand_producer(name)
    if spec["credential"] is None:
        raise kernel.ClaimError(f"unknown producer: {name!r}")
    value = os.environ.get(spec["credential"])
    if not value:
        raise kernel.ClaimError(f"producer {name!r} needs {spec['credential']} set")
    return value


def _scan_workspace(ws: str) -> dict:
    """What `ws` already holds: whether it is marked (`.reticuli` exists),
    whether a recipe is sealed there, and how many events its session
    trace has recorded."""
    store = os.path.join(ws, kernel.STORE)
    marked = os.path.isdir(store)
    sealed = marked and os.path.isfile(os.path.join(ws, kernel.MANIFEST))
    trace_path = os.path.join(ws, hooks.TRACE)
    events = 0
    if os.path.isfile(trace_path):
        with open(trace_path, "r", encoding="utf-8") as f:
            events = sum(1 for _ in f)
    return {"marked": marked, "sealed": sealed, "events": events}


def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a session workspace: create it and its `.reticuli`
    store, then -- unless `no_agent` withholds the handshake -- wire the
    coding-agent hooks into it (`hooks.install`)."""
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    agent = None if no_agent else hooks.install(ws)
    return {"ws": ws, "agent": agent}


def run(cmd: str, ws: str = None) -> int:
    """Run one shell command inside `ws` (the current directory if `ws` is
    absent) and return the child's exit code unchanged, so a session
    script can use a run's result as its own predicate."""
    proc = subprocess.run(cmd, shell=True, cwd=ws or os.getcwd())
    return proc.returncode
