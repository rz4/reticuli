"""Session setup, the traced run, and producer preflight.

`init` marks a workspace and, because an agent handshake is not a separate
concept to learn, can wire the agent in the same act.

`run` is a TRANSPARENT boundary: it observes the command and returns the
child's exit code UNCHANGED, so a session can use `ret run` as a predicate
the way it uses any command.  A wrapper that swallowed a failure would turn a
red run green, which is the one thing a wrapper must never do.

A NAMED producer preflights before any money moves.  Two shapes exist: an SDK
producer needs a credential in the environment, and a CLI producer needs its
binary on PATH.  Either way the refusal is one line on stderr BEFORE a room
is built — not a traceback from inside one — and an adapter that ships must
be reachable by name, because `--producer codex` once fell through to the
bare binary, opened an interactive UI, and died on the piped prompt.  A
producer is still ANY program: a name the tables do not know passes through
verbatim.
"""
import json
import os
import shutil
import subprocess
import sys

from .. import __version__, _util, feedback, hooks, kernel

#: SDK producers: the name a user types, and the credential it forwards.
_PRODUCERS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
#: CLI producers: the name a user types, and the binary that must be present.
_CLI_PRODUCERS = {
    "codex": "codex",
    "claude": "claude",
}
#: Variables handed through to a producer beside its credential — endpoint
#: and budget knobs the caller sets deliberately.
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE",
                         "RETICULI_AGENT_TURNS")


def _version_line() -> str:
    """The tool naming itself — diagnostic, never identity."""
    return f"ret {__version__}"


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _package_root() -> str:
    """The directory holding this `reticuli` package, for a child's path."""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def _expand_producer(name: str):
    """Resolve a producer NAME to a command, or pass a command through.

    Returns `(command, env)`; `env` is None for a passed-through command,
    because a program the caller wrote needs nothing from us.
    """
    if name in _CLI_PRODUCERS:
        binary = _CLI_PRODUCERS[name]
        if not shutil.which(binary):
            raise kernel.ClaimError(
                f"the {name} producer needs {binary!r} on PATH; install it "
                f"or name a producer command instead")
        env = {"PYTHONPATH": _package_root()}
        for key in _PRODUCER_PASSTHROUGH:
            if os.environ.get(key):
                env[key] = os.environ[key]
        return (f"{sys.executable} -m reticuli.producers.{name}", env)
    if name in _PRODUCERS:
        key = _PRODUCERS[name]
        if not os.environ.get(key):
            raise kernel.ClaimError(
                f"the {name} producer needs {key} in the environment; set it "
                f"or name a producer command instead")
        env = {"PYTHONPATH": _package_root(), key: os.environ[key]}
        for extra in _PRODUCER_PASSTHROUGH:
            if os.environ.get(extra):
                env[extra] = os.environ[extra]
        return (f"{sys.executable} -m reticuli.producers.{name}", env)
    # A producer is any program.  The name table must not swallow commands.
    return (name, None)


def _scan_workspace(workspace: str) -> dict:
    """The authoring triad for a session directory."""
    return feedback.advise(workspace)


def init(workspace: str, no_agent: bool = False, agent: str = None) -> dict:
    """Mark a workspace, git-natively, and wire the agent if asked."""
    where = os.path.abspath(workspace)
    _ensure(where)
    _ensure(os.path.join(where, kernel.STORE))
    ignore = os.path.join(where, ".gitignore")
    wanted = [".reticuli/ledger.jsonl", ".reticuli/draft.jsonl",
              ".reticuli/scratch/", ".reticuli/usage.json", ".launcher/"]
    present = []
    if os.path.isfile(ignore):
        with open(ignore, encoding="utf-8") as handle:
            present = handle.read().splitlines()
    missing = [line for line in wanted if line not in present]
    if missing:
        with open(ignore, "a", encoding="utf-8") as handle:
            if present and present[-1].strip():
                handle.write("\n")
            handle.write("\n".join(missing) + "\n")
    wired = None
    if agent and not no_agent:
        wired = hooks.install(where, agent)
    return {"workspace": where, "store": os.path.join(where, kernel.STORE),
            "agent": agent if wired else None, "wired": wired}


def run(command: str, workspace: str) -> int:
    """Observe a command, and hand its exit code straight back."""
    where = os.path.abspath(workspace)
    if not os.path.isdir(where):
        raise kernel.ClaimError(f"no such directory: {workspace}")
    if os.path.isdir(os.path.join(where, kernel.STORE)):
        _util.trace_append(where, {"event": "bash", "cmd": command,
                                   "via": "shell", "when": _util.stamp()})
    done = subprocess.run(command, shell=True, cwd=where, check=False)
    return done.returncode


def hook(payload_text: str, workspace: str):
    """Translate one agent payload into an observation, or into nothing."""
    try:
        payload = json.loads(payload_text or "{}")
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return hooks.event(payload, workspace)
