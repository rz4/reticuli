"""Handlers: the action verbs `cli.py`'s argument parser dispatches to
(spec/layers.md, "surface"). Every function here returns a plain result
-- a dict, or, for `run`, the child's own exit code -- and never prints;
`report.py` is where a result becomes terminal output.

`init` marks a plain directory as a reticuli workspace: a `.reticuli`
store, so every later verb (`claims`, `deps`, `status`, ...) has
somewhere to read from, and -- unless `no_agent` -- the coding-agent
hooks (`hooks.install`) wired into its Claude Code project settings. A
second call on an already-marked workspace is a no-op on the store (it
already exists) and leaves `hooks.install`'s own idempotence to decide
the rest.

`run` executes an arbitrary shell command with a workspace as its
working directory and hands back the child's exit code completely
unwrapped -- never raised, never translated -- so a session can chain
it as a predicate (`ret run "pytest" && ret seal`).

A *named* producer is a short word (`RETICULI_PRODUCER=codex`, not a
full shell command) standing for one of a short list of known external
producers (`_PRODUCERS`): each names the environment variable that
holds its credential (or `None`, for one that authenticates some other
way) and the command line that invokes it. `_expand_producer` resolves
a name to its command; `_ensure` preflights the credential it declares
-- refusing before a subprocess is spawned, and money is spent, rather
than after. A `RETICULI_PRODUCER` value that is not a known name is
already a literal command and passes through untouched. `run` forwards
the resolved producer, plus whatever of `_PRODUCER_PASSTHROUGH`'s
price/turn-budget/base-URL knobs the parent environment set, into the
child's scrubbed environment -- the same discipline `launcher.py`
already applies to a launched claim.
"""
import os
import subprocess
import sys

from .. import hooks
from .. import kernel

_RETICULI_VERSION = "3.0"

# Environment carried into every child `run` spawns, unconditionally --
# enough for a shell and its ordinary tools to work at all.
_KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TZ", "HOME")

# Carried through only when the parent environment sets it: a named
# producer's own knobs, never invented by `run` itself.
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

# Known short names for `RETICULI_PRODUCER`, each a credential
# environment variable (or `None`, for a producer that authenticates
# some other way, e.g. a locally signed-in CLI) and the command line
# the name expands to.
_PRODUCERS = {
    "openai": {
        "credential": "OPENAI_API_KEY",
        "command": f"{sys.executable} -m reticuli.producers.openai",
    },
    "anthropic": {
        "credential": "ANTHROPIC_API_KEY",
        "command": f"{sys.executable} -m reticuli.producers.anthropic",
    },
    "codex": {
        "credential": None,
        "command": "codex exec --dangerously-bypass-approvals-and-sandbox",
    },
}


class HandlerError(Exception):
    """A handler refusal: a plain message, no exit code of its own --
    `cli.py` decides how a raised `HandlerError` is reported.
    """


# ===========================================================================
# Named producers: resolve a short name, preflight its credential.
# ===========================================================================


def _ensure(name: str) -> None:
    """Preflight a named producer's credential before anything is
    spawned (and money spent): refuse if `_PRODUCERS[name]`'s
    credential environment variable is declared and unset. A name this
    module does not know, or one whose producer declares no credential
    at all, always passes.
    """
    spec = _PRODUCERS.get(name)
    if spec is None:
        return
    credential = spec.get("credential")
    if credential and not os.environ.get(credential):
        raise HandlerError(f"producer {name!r} needs {credential} set")


def _expand_producer(value: str) -> str:
    """`value` as a `RETICULI_PRODUCER` setting, expanded: a name in
    `_PRODUCERS` becomes its command line, after `_ensure` preflights
    its credential; anything else is already a literal shell command
    and passes through untouched.
    """
    if value in _PRODUCERS:
        _ensure(value)
        return _PRODUCERS[value]["command"]
    return value


# ===========================================================================
# init: mark a plain directory as a reticuli workspace.
# ===========================================================================


def _scan_workspace(ws: str) -> dict:
    """A workspace's shape at a glance: whether it already carries a
    `.reticuli` store, and the sealed claim names already inside it --
    `init`'s idempotence reads this rather than re-deriving it inline.
    """
    store = os.path.join(ws, kernel.STORE)
    sealed = os.path.join(store, "sealed")
    names = []
    if os.path.isdir(sealed):
        names = sorted(
            n for n in os.listdir(sealed) if os.path.isdir(os.path.join(sealed, n))
        )
    return {"exists": os.path.isdir(store), "claims": names}


def _version_line() -> str:
    """The one-line version banner `init` and `--version` share."""
    return f"reticuli {_RETICULI_VERSION}"


def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a reticuli workspace: create its `.reticuli` store
    if missing, and -- unless `no_agent` -- wire the coding-agent hooks
    (`hooks.install`) into its Claude Code project settings. Idempotent:
    a second call makes the store (already present) a no-op, and
    `hooks.install`'s own idempotence decides the rest.
    """
    before = _scan_workspace(ws)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)

    result = {
        "status": "already initialized" if before["exists"] else "initialized",
        "workspace": ws,
        "version": _version_line(),
    }
    if not no_agent:
        result["hooks"] = hooks.install(ws)
    return result


# ===========================================================================
# run: a session's own predicate, the child's exit code unwrapped.
# ===========================================================================


def _child_env() -> dict:
    """The scrubbed environment handed to `run`'s child: `_KEEP_ENV`
    unconditionally, a resolved `RETICULI_PRODUCER` (`_expand_producer`)
    when the parent sets one, and whichever of `_PRODUCER_PASSTHROUGH`'s
    knobs the parent environment also sets.
    """
    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}

    producer = os.environ.get("RETICULI_PRODUCER")
    if producer:
        env["RETICULI_PRODUCER"] = _expand_producer(producer)

    for name in _PRODUCER_PASSTHROUGH:
        if name in os.environ:
            env[name] = os.environ[name]

    return env


def run(cmd: str, ws: str) -> int:
    """Run `cmd` as a shell command with `ws` as its working directory,
    and hand back the child's exit code completely unwrapped -- never
    raised, never translated -- so a session can chain it as a
    predicate (`ret run "pytest" && ret seal`).
    """
    proc = subprocess.run(cmd, shell=True, cwd=ws, env=_child_env())
    return proc.returncode
