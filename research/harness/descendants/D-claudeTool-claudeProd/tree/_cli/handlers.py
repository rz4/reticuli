"""Session setup, the traced run, and producer preflight.

`init` marks a workspace (and wires the agent, because that is not a separate
concept to learn). `run` is a transparent boundary: it returns the child's
exit code UNCHANGED, so a session can use it as a predicate the way it uses
any command. And a NAMED producer is preflighted -- a missing CLI or
credential is one line on stderr before a room is built or any money moves.
"""
import os
import shutil
import subprocess
import sys

from .. import hooks
from .. import kernel
from .._util import trace_append

#: Producers reached through a vendor SDK: name -> the credential they need.
_PRODUCERS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

#: Producers that are a command-line tool on PATH: name -> the binary.
#: An adapter no --producer name reaches is unreachable, so both tables are
#: expanded by the same function and both are named in `ret help rebuild`.
_CLI_PRODUCERS = {
    "codex": "codex",
    "claude": "claude",
}

#: Variables a producer may receive past the scrub, when the caller set them.
#: The only road an inherited value travels is the caller's own hand.
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE",
                         "RETICULI_AGENT_TURNS")


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _package_root() -> str:
    """Where this package lives, so an adapter imports THIS reticuli."""
    return os.path.dirname(os.path.dirname(os.path.abspath(
        os.path.dirname(__file__))))


def _version_line() -> str:
    from .. import __version__
    return f"ret {__version__}"


def _expand_producer(producer: str):
    """A producer name becomes its adapter; anything else passes through.

    A producer is ANY program -- the name table must not swallow commands --
    but a name the tool ships an adapter for must reach that adapter, not the
    bare binary of the same name, which opens an interactive UI and dies on a
    piped prompt.
    """
    if not producer:
        raise kernel.ClaimError("name a producer: --producer <name|command>")
    name, _, model = producer.partition(":")
    name = name.strip()
    if name in _CLI_PRODUCERS:
        binary = _CLI_PRODUCERS[name]
        if not shutil.which(binary):
            raise kernel.ClaimError(
                f"the {name} producer needs the {binary!r} command on your "
                f"PATH; install it, or pass a producer command directly")
    elif name in _PRODUCERS:
        variable = _PRODUCERS[name]
        if not os.environ.get(variable):
            raise kernel.ClaimError(
                f"the {name} producer needs {variable} in your environment; "
                f"set it, or pass a producer command directly")
    else:
        return producer, None
    os.environ["RETICULI_VENDOR"] = name
    if model:
        os.environ["RETICULI_MODEL"] = model
    command = f"{sys.executable} -m reticuli.producers.{name}"
    environment = {"PYTHONPATH": _package_root()}
    for variable in _PRODUCER_PASSTHROUGH:
        if os.environ.get(variable):
            environment[variable] = os.environ[variable]
    if model:
        environment["RETICULI_MODEL"] = model
    if name in _PRODUCERS and os.environ.get(_PRODUCERS[name]):
        environment[_PRODUCERS[name]] = os.environ[_PRODUCERS[name]]
    return command, environment


def _scan_workspace(ws: str) -> list:
    """Every ordinary file in a workspace, as a view wants to list it."""
    found = []
    for base, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.startswith("."):
                continue
            found.append(os.path.relpath(os.path.join(base, name), ws))
    return sorted(found)


GITIGNORE = """# reticuli: residue is local, identity is committed
.reticuli/ledger.jsonl
.reticuli/draft.jsonl
.reticuli/scratch/
.reticuli/usage.json
.reticuli/parts.json
.launcher/
"""


def init(workspace: str, agent: str | None = None,
         no_agent: bool = False) -> dict:
    """Mark a workspace, git-natively, and wire the agent unless told not to."""
    _ensure(workspace)
    _ensure(os.path.join(workspace, kernel.STORE))
    ignore = os.path.join(workspace, ".gitignore")
    if not os.path.isfile(ignore):
        with open(ignore, "w", encoding="utf-8") as handle:
            handle.write(GITIGNORE)
    else:
        with open(ignore, encoding="utf-8") as handle:
            text = handle.read()
        if "ledger.jsonl" not in text:
            with open(ignore, "a", encoding="utf-8") as handle:
                handle.write("\n" + GITIGNORE)
    result = {"workspace": workspace, "agent": None, "wired": []}
    if agent and not no_agent:
        wiring = hooks.install(workspace, agent)
        result["agent"] = agent
        result["wired"] = wiring["wired"]
        result["status"] = wiring["status"]
    return result


def run(command: str, workspace: str) -> int:
    """Run a command in the session and remember it. The child's code stands.

    A silent wrapper: only the child's streams reach the terminal, and its
    exit code is returned unchanged, so a red run cannot go green.
    """
    _ensure(workspace)
    if os.path.isdir(os.path.join(workspace, kernel.STORE)):
        trace_append(workspace, {"event": "bash", "cmd": command,
                                 "via": "shell"})
    done = subprocess.run(command, shell=True, cwd=workspace, check=False)
    return done.returncode
