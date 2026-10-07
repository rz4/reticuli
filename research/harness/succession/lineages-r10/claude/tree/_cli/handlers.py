"""reticuli._cli.handlers: session setup, traced run, producer preflight.

`init` marks a directory as a reticuli session: it creates the `.reticuli`
store (the same marker `reticuli.hooks` and `reticuli.authoring` look for)
and, unless `no_agent` withholds it, wires the coding-agent hooks into the
project (`reticuli.hooks.install`). It reports exactly what it created,
never what was already there.

`run` executes one command inside a workspace and returns the child's
exit code unchanged -- so a session loop can use it as a predicate (a
gate command that exits 0 means done). When `cmd` names a known producer
(`_PRODUCERS`) rather than a literal shell command, `run` preflights that
producer's credential (`_ensure`) before spending anything, expands it to
its real invocation (`_expand_producer`), and runs it under a minimal,
scrubbed environment -- the host's full environment is never handed to
a producer, only a base allowlist, the producer's own credential, and
the declared tuning variables (`_PRODUCER_PASSTHROUGH`). A literal command
runs under the caller's own environment, since it is the caller's gate,
not a producer spend. Either way, when `ws` is already a session, the
command is appended to its draft trace -- the same file a Claude Code
hook event lands in -- so a manually run gate and an agent's own
actions read back as one session.

Stdlib only.
"""
import json
import os
import subprocess
import sys
import time
import platform

from reticuli import _util
from reticuli import hooks
from reticuli import kernel

STORE = ".reticuli"
TRACE = ".reticuli/draft.jsonl"
SESSION_FILE = ".reticuli/session.json"

# known producers: a short name a session can pass to `run` instead of a
# literal command, the real invocation it expands to, and the credential
# `_ensure` preflights before anything is spent.
_PRODUCERS = {
    "codex": {"command": "codex exec", "credential": "OPENAI_API_KEY"},
    "claude": {"command": "claude -p", "credential": "ANTHROPIC_API_KEY"},
}

# variables let through the producer environment scrub -- never the
# caller's full environment, since a producer spends real money and
# should see no secret it was not handed.
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")

_BASE_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "LANGUAGE", "TZ")


# ---- the session marker -----------------------------------------------------

def _is_session(ws) -> bool:
    return bool(ws) and os.path.isdir(os.path.join(ws, STORE))


def _trace(ws: str, entry: dict) -> None:
    """Append one entry to the session's draft trace -- the same file
    `reticuli.hooks` and `reticuli.authoring` read."""
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _scan_workspace(ws: str) -> set:
    """Every path presently under `ws`, as forward-slash relative strings
    -- `init`'s before/after snapshot, so it can report what it actually
    created rather than guessing from what it attempted."""
    found = set()
    if not os.path.isdir(ws):
        return found
    for root, dirs, files in os.walk(ws):
        rel_root = os.path.relpath(root, ws)
        for name in dirs + files:
            rel = name if rel_root == os.curdir else f"{rel_root}/{name}"
            found.add(rel.replace(os.sep, "/"))
    return found


def _version_line() -> str:
    """A one-line banner identifying this implementation: the claim
    format it speaks, and the host it ran on -- stamped into a session's
    record at `init`."""
    return (f"reticuli/format-{kernel.FORMAT} "
            f"python/{platform.python_version()} {sys.platform}")


# ---- init --------------------------------------------------------------------

def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a reticuli session.

    Creates the `.reticuli` store and a small session record if neither
    is already present, then (unless `no_agent`) wires the coding-agent
    hooks into the project. Idempotent: a second call against an
    already-marked workspace creates nothing further and reports an
    empty `created` list.
    """
    ws = os.path.abspath(ws)
    os.makedirs(ws, exist_ok=True)
    before = _scan_workspace(ws)

    store = os.path.join(ws, STORE)
    os.makedirs(store, exist_ok=True)

    session_path = os.path.join(ws, SESSION_FILE)
    if not os.path.isfile(session_path):
        _util.write_json(session_path, {
            "version": _version_line(),
            "started": _util.stamp(),
        })

    wired = []
    if not no_agent:
        result = hooks.install(ws)
        wired = result.get("wired", [])

    created = sorted(_scan_workspace(ws) - before)
    return {"ok": True, "path": ws, "created": created, "wired": wired}


# ---- producer preflight and expansion --------------------------------------

def _ensure(name: str) -> None:
    """Refuse, before anything is spent, a producer `run` does not know
    or whose credential is not present in the host environment."""
    spec = _PRODUCERS.get(name)
    if spec is None:
        raise kernel.ClaimError(f"unknown producer {name!r}")
    credential = spec.get("credential")
    if credential and credential not in os.environ:
        raise kernel.ClaimError(
            f"producer {name!r} needs {credential} set in the environment")


def _expand_producer(name: str) -> str:
    """The shell command a named producer actually runs: its base
    invocation, with `RETICULI_AGENT_TURNS` folded in as a turn-ceiling
    flag when the caller declared one."""
    cmd = _PRODUCERS[name]["command"]
    turns = os.environ.get("RETICULI_AGENT_TURNS")
    if turns:
        cmd = f"{cmd} --max-turns {turns}"
    return cmd


def _producer_env(name: str) -> dict:
    """The scrubbed environment a named producer runs under: a minimal
    host allowlist, its own credential, and the declared passthrough
    variables -- never the caller's full environment."""
    env = {k: os.environ[k] for k in _BASE_ENV_KEEP if k in os.environ}
    credential = _PRODUCERS[name].get("credential")
    if credential and credential in os.environ:
        env[credential] = os.environ[credential]
    for k in _PRODUCER_PASSTHROUGH:
        if k in os.environ:
            env[k] = os.environ[k]
    return env


# ---- run ---------------------------------------------------------------------

def run(cmd: str, ws: str = None) -> int:
    """Run `cmd` inside `ws` and return the child's exit code unchanged.

    `cmd` is either a literal shell command, run under the caller's own
    environment, or the name of a known producer (`_PRODUCERS`), which
    is preflighted (`_ensure`), expanded (`_expand_producer`), and run
    under a scrubbed environment instead. Either way, when `ws` is
    already a session, the call is appended to its draft trace.
    """
    ws_abs = os.path.abspath(ws) if ws else os.getcwd()

    if cmd in _PRODUCERS:
        _ensure(cmd)
        shell_cmd = _expand_producer(cmd)
        run_env = _producer_env(cmd)
    else:
        shell_cmd = cmd
        run_env = dict(os.environ)

    if _is_session(ws_abs):
        _trace(ws_abs, {"event": "bash", "cmd": cmd, "ts": time.time()})

    proc = subprocess.run(shell_cmd, shell=True, cwd=ws_abs, env=run_env, check=False)
    return proc.returncode
