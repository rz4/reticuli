"""reticuli._cli.handlers: session setup, traced run, producer preflight
(spec/layers.md "surface"; checks/handlers_check.py is this module's
definition).

`init` marks a workspace: it creates the directory and its `.reticuli/`
store, then wires the Claude Code hook handshake (`hooks.install`) unless
`no_agent` withholds it -- a session worked through the bare CLI still
needs to trace itself, which is what `run` is for. `run` is the CLI's own
predicate form of a gate command: it runs `cmd` in the workspace, appends
it to the session trace the same shape the installed hook would
(`hooks.event`'s own Bash branch), and hands back the child's exit code
unchanged, so a session can chain on it (`ret run "pytest" && ret seal`).
`_ensure` and `_expand_producer` preflight a named producer's credential
before a rebuild spends anything on it, expanding a short name to the
shell command `kernel.rebuild` runs plus the caller-environment variables
(`_PRODUCER_PASSTHROUGH`) that should reach it. `_scan_workspace` and
`_version_line` are the small reporting primitives the rest of the
surface reaches for. Stdlib only.
"""
import json
import os
import platform
import subprocess
import sys
import time

from reticuli import hooks, kernel

TRACE = ".reticuli/draft.jsonl"

_VERSION = "2.2"

# Environment variables a caller's own shell may carry that a named
# producer should see too -- never credentials (those live in _PRODUCERS
# below, and are checked, not relayed blindly).
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

# Named shortcuts for `--producer`: a shell command template and the
# credential environment variable `_ensure` checks before anything runs.
_PRODUCERS = {
    "codex": {
        "command": "codex exec --full-auto --skip-git-repo-check",
        "credential": "OPENAI_API_KEY",
    },
    "claude": {
        "command": "claude -p --dangerously-skip-permissions",
        "credential": "ANTHROPIC_API_KEY",
    },
}


# -- producer preflight: a credential is checked before anything spends ----

def _ensure(name):
    """Refuse in words, before a named producer spends anything: a
    producer `_PRODUCERS` names must have its declared credential already
    in the environment. An unnamed producer (a raw shell command) carries
    no tracked credential, and is not this function's business."""
    info = _PRODUCERS.get(name)
    if info is None:
        return
    credential = info.get("credential")
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(
            f"producer {name!r} needs {credential} set in the environment")


def _expand_producer(producer):
    """`producer` -- a name `_PRODUCERS` knows, or a raw shell command --
    expanded to `(command, env)`: the shell command `kernel.rebuild` runs,
    and the environment variables it should reach the producer through,
    read from the caller's own environment (`_PRODUCER_PASSTHROUGH`).
    Preflights the credential first, so a missing one refuses before the
    expansion is even used."""
    _ensure(producer)
    info = _PRODUCERS.get(producer)
    command = info["command"] if info else producer
    env = {k: os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ}
    return command, env


# -- reporting primitives ----------------------------------------------

def _version_line():
    """One diagnostic line naming this tool and its host interpreter --
    the whole of `--version`'s output, never parsed by anything."""
    return f"reticuli {_VERSION} (CPython {platform.python_version()}, {sys.platform})"


def _scan_workspace(ws):
    """`ws`'s own account of itself: whether it is tracked at all
    (`.reticuli/` present), its sealed claims (mirroring
    `registry.claims`'s `{name, root, phase}` shape), and how many
    session-trace events have been recorded so far."""
    store = os.path.join(ws, kernel.STORE)
    if not os.path.isdir(store):
        return {"tracked": False, "claims": [], "trace_events": 0}

    sealed_root = os.path.join(store, "sealed")
    found = []
    if os.path.isdir(sealed_root):
        for name in sorted(os.listdir(sealed_root)):
            claim_dir = os.path.join(sealed_root, name)
            if not os.path.isdir(claim_dir):
                continue
            try:
                manifest = kernel.read_manifest(claim_dir)
            except kernel.ClaimError:
                continue
            found.append({"name": manifest["name"], "root": manifest["root"],
                           "phase": kernel.phase(claim_dir)})

    trace_path = os.path.join(ws, TRACE)
    events = 0
    if os.path.isfile(trace_path):
        with open(trace_path, "r", encoding="utf-8") as f:
            events = sum(1 for line in f if line.strip())

    return {"tracked": True, "claims": found, "trace_events": events}


# -- init: mark a workspace ----------------------------------------------

def init(ws, no_agent=False):
    """Mark `ws` as a tracked workspace: create the directory and its
    `.reticuli/` store, then wire the Claude Code hook handshake unless
    `no_agent` withholds it (a bare CLI session still traces itself,
    through `run`, either way)."""
    os.makedirs(ws, exist_ok=True)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    if not no_agent:
        hooks.install(ws)
    return _scan_workspace(ws)


# -- run: the CLI's own traced predicate ----------------------------------

def run(cmd, ws):
    """Run `cmd` in `ws` and hand back the child's exit code unchanged,
    so a session can use it as a predicate. Where `ws` is a tracked
    workspace, the command is appended to the session trace in the same
    shape the installed hook records a Bash tool call in
    (`hooks.event`'s Bash branch), so a session worked through the bare
    CLI is exactly as sealable as one worked through an agent."""
    proc = subprocess.run(cmd, shell=True, cwd=ws)
    rc = proc.returncode

    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        path = os.path.join(ws, TRACE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "bash", "cmd": cmd, "ts": time.time()},
                                sort_keys=True))
            f.write("\n")

    return rc
