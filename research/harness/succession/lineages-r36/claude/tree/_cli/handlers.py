"""Session setup, the traced run, and the producer preflight.

Three jobs the CLI needs before any verdict exists: marking a workspace
(and wiring an agent by the same act, since there is no second concept to
learn), running a command transparently while observing it, and turning a
producer NAME into something runnable.

THE PREFLIGHT IS THE POINT of the name table. A producer costs money, so a
missing credential or a missing binary must be one line on stderr BEFORE a
room is built -- never a traceback from inside the room after the bill. And
every adapter that SHIPS must be reachable by a name: `codex` once shipped
while the table knew only the SDK pair, so `--producer codex` ran the bare
binary, which opens an interactive UI and died on the piped prompt.
"""
import os
import shutil
import subprocess
import sys

from .. import _util
from .. import feedback
from .. import hooks
from .. import kernel

#: SDK producers: the name, and the credential this tool forwards for it.
#: Forwarded only because the USER named the producer -- it is the one road
#: an inherited credential may travel, and only by the caller's hand.
_PRODUCERS = {"openai": "OPENAI_API_KEY",
              "anthropic": "ANTHROPIC_API_KEY"}

#: CLI producers: the name, and the binary whose presence it needs. Each
#: reaches an adapter module, never the bare binary.
_CLI_PRODUCERS = {"codex": "codex", "claude": "claude"}

#: variables a producer may need that are not credentials: an endpoint
#: override, a price table, a turn budget. Handed over, never guessed at.
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE",
                         "RETICULI_AGENT_TURNS")

GITIGNORE = """# reticuli: residue, never identity
.reticuli/ledger.jsonl
.reticuli/scratch/
.reticuli/usage.json
.reticuli/draft.jsonl
.launcher/
"""


def _version_line() -> str:
    from .. import __version__
    return f"ret {__version__}"


def _ensure(path: str) -> str:
    """The workspace exists and has a store. Nothing else is assumed."""
    where = os.path.abspath(path)
    os.makedirs(os.path.join(where, kernel.STORE), exist_ok=True)
    return where


def init(path: str, agent: str | None = None,
         no_agent: bool = False) -> dict:
    """Mark a workspace: a store, a .gitignore, and the agent wiring."""
    where = _ensure(path)
    ignore = os.path.join(where, ".gitignore")
    existing = ""
    if os.path.isfile(ignore):
        with open(ignore, encoding="utf-8") as handle:
            existing = handle.read()
    if "ledger.jsonl" not in existing:
        with open(ignore, "w", encoding="utf-8") as handle:
            handle.write(existing + ("\n" if existing and
                                     not existing.endswith("\n") else "")
                         + GITIGNORE)
    found = {"path": where, "store": kernel.STORE, "gitignore": ignore,
             "agent": None, "wired": [], "status": "initialized"}
    if no_agent or agent is None:
        return found
    wired = hooks.install(where, agent)
    found["agent"] = agent
    found["wired"] = wired.get("wired") or []
    found["status"] = wired.get("status")
    return found


def run(command, workspace: str = ".") -> int:
    """Run a command inside a workspace and observe it.

    The child's streams ARE the output and its exit code is returned
    unchanged, so this can be used as a predicate exactly as the bare
    command could. A wrapper that swallowed a failure would turn a red run
    green.
    """
    where = _ensure(workspace)
    text = command if isinstance(command, str) else " ".join(command)
    _util.trace_append(os.path.join(where, ".reticuli", "draft.jsonl"),
                       {"event": "bash", "cmd": text,
                        "ts": _now(), "via": "shell"})
    done = subprocess.run(text, shell=True, cwd=where, check=False)
    return done.returncode


def _now() -> float:
    import time
    return round(time.time(), 3)


def _scan_workspace(workspace: str) -> dict:
    """What this session has observed, declared, and left unresolved."""
    return feedback.advise(workspace)


def _expand_producer(named: str):
    """A producer name into a command, with whatever it needs handed over.

    A producer is ANY PROGRAM: a name the table does not know passes
    through verbatim, so the table can never swallow a command. A name it
    does know preflights first -- the binary on PATH, the credential in the
    environment -- because the alternative is discovering it after the
    money moved.
    """
    text = (named or "").strip()
    if not text:
        raise kernel.ClaimError("no producer was named")
    head, _, model = text.partition(":")
    if head not in _PRODUCERS and head not in _CLI_PRODUCERS:
        return text, None
    env = {"PYTHONPATH": os.pathsep.join(
        p for p in [os.path.dirname(os.path.dirname(
            os.path.abspath(os.path.dirname(__file__)))),
            os.environ.get("PYTHONPATH", "")] if p)}
    if model:
        env["RETICULI_MODEL"] = model
    env["RETICULI_VENDOR"] = head
    for name in _PRODUCER_PASSTHROUGH:
        if os.environ.get(name):
            env[name] = os.environ[name]
    if head in _CLI_PRODUCERS:
        binary = _CLI_PRODUCERS[head]
        if not shutil.which(binary):
            raise kernel.ClaimError(
                f"the {head} producer needs the {binary!r} command, and it "
                f"is not on PATH")
    else:
        key = _PRODUCERS[head]
        if not os.environ.get(key):
            raise kernel.ClaimError(
                f"the {head} producer needs {key} in the environment, and "
                f"it is not set: nothing was built and nothing was spent")
        env[key] = os.environ[key]
    return f"{sys.executable} -m reticuli.producers.{head}", env
