"""Session setup, a traced run, and producer preflight (`spec/layers.md`'s
surface layer, the half of it that is not pure rendering).

`init` marks a directory as an authoring session: the same `.reticuli/`
marker `hooks._has_session` and the trace readers in `feedback`/`authoring`
already recognize, plus -- unless `no_agent` -- the coding-agent hooks
wired into it (`hooks.install`). `run` is the non-agent way to add to that
same trace: it runs one shell command for real in the session directory,
appends a `bash` trace entry in the exact vocabulary `hooks.event` writes,
and returns the child's exit code UNCHANGED, so a session script can use
it as a predicate (`ret run "pytest" && ret seal`) without this module
ever turning a nonzero exit into a refusal of its own.

A named producer is typed as a short word (`codex`, `claude`, ...), not a
shell command -- `_expand_producer` resolves it against `_PRODUCERS` and
`_ensure`s its credential is present BEFORE anything is spent, since a
missing key is cheaper to catch here than after a producer has already
billed for a call that was never going to finish. `_PRODUCER_PASSTHROUGH`
names the ambient variables a producer is handed past the environment
scrub -- never a secret, only budget/endpoint hints a human set for
themselves. `_scan_workspace` is the same preflight's other half: a quick
read of what a session's trace shows has happened so far.

Stdlib only.
"""
import json
import os
import platform
import subprocess
import sys
import time

from .. import hooks
from .. import kernel

TRACE = ".reticuli/draft.jsonl"

_VERSION = "2.2"

# -- named producers: a short word, not a shell command ---------------------

_PRODUCERS = {
    "codex": {"cmd": "codex exec --full-auto", "requires": "OPENAI_API_KEY"},
    "claude": {"cmd": "claude -p --dangerously-skip-permissions",
               "requires": "ANTHROPIC_API_KEY"},
    "gemini": {"cmd": "gemini -y", "requires": "GEMINI_API_KEY"},
}

_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")


def _ensure(cond: bool, msg: str) -> None:
    """Raise `kernel.ClaimError(msg)` unless `cond` -- the one place a
    preflight refuses, so every check in this module reads the same way."""
    if not cond:
        raise kernel.ClaimError(msg)


def _expand_producer(name: str, env: dict = None) -> tuple:
    """A CLI-typed producer name, expanded to `(command, producer_env)`.

    A name found in `_PRODUCERS` becomes its full command, after
    preflighting the credential it declares -- refused here, before a
    human spends real money on a producer that was never going to run.
    A name not found passes through unchanged, as a literal shell
    command. `producer_env` carries only the `_PRODUCER_PASSTHROUGH`
    variables that are actually set in `env` (the ambient environment by
    default) -- the only road one of them travels into a producer's room.
    """
    env = os.environ if env is None else env
    spec = _PRODUCERS.get(name)
    if spec is not None:
        _ensure(spec["requires"] in env,
                f"refused: producer {name!r} needs ${spec['requires']}")
        cmd = spec["cmd"]
    else:
        cmd = name
    producer_env = {k: env[k] for k in _PRODUCER_PASSTHROUGH if k in env}
    return cmd, producer_env


# -- reading a session's trace ----------------------------------------------

def _read_trace(ws: str) -> list:
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _append_trace(ws: str, entry: dict) -> None:
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _scan_workspace(ws: str) -> dict:
    """What a session's trace shows has happened so far: how many of each
    event kind, and every path it has written -- the quick picture a
    human checks before spending real money on a producer."""
    events = _read_trace(ws)
    counts = {}
    written = []
    for e in events:
        kind = e.get("event", "?")
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "write":
            path = e.get("path")
            if path and path not in written:
                written.append(path)
    return {"events": len(events), "counts": counts, "written": written}


# -- version ------------------------------------------------------------

def _version_line() -> str:
    """One line identifying this build -- a CLI's `--version` output."""
    return f"reticuli {_VERSION} (python {platform.python_version()}, {sys.platform})"


# -- session setup and a traced run -----------------------------------------

def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as an authoring session: the `.reticuli/` directory any
    trace-reading layer recognizes, and -- unless `no_agent` -- the
    coding-agent hooks wired into it (`hooks.install`)."""
    ws = os.path.abspath(ws)
    os.makedirs(os.path.join(ws, ".reticuli"), exist_ok=True)
    agent = None
    if not no_agent:
        agent = hooks.install(ws)
    return {"ok": True, "ws": ws, "agent": agent}


def run(cmd: str, ws: str) -> int:
    """Run `cmd` for real in the session at `ws`, appending a `bash`
    trace entry in the same vocabulary `hooks.event` writes -- a non-agent
    way to add to the same trace `feedback.advise` and
    `authoring.build_claim` read back later. Returns the child's exit
    code UNCHANGED, so a caller can use this as a predicate.
    """
    ws = os.path.abspath(ws)
    if os.path.isdir(os.path.join(ws, ".reticuli")):
        _append_trace(ws, {"event": "bash", "cmd": cmd, "ts": time.time()})
    proc = subprocess.run(cmd, shell=True, cwd=ws)
    return proc.returncode
