"""Session handlers: workspace setup (`init`), a traced run (`run`), and
named-producer preflight (`_ensure`/`_expand_producer`) -- the CLI's own
action layer for the verbs that do work rather than merely read or render
a claim already on disk (spec/layers.md's surface layer). This module
reaches `reticuli.kernel` and the layers below it, never `reticuli._kernel`
directly.

A workspace is marked by its own `.reticuli` store (`kernel.STORE`) -- the
same directory a sealed claim keeps its manifest and ledger under, so a
workspace later built into a claim (`authoring.build_claim`) is already
standing on the right ground. `init` makes that mark and, unless told
`no_agent`, wires the coding-agent handshake (`hooks.install`) so a traced
session can begin; a workspace already marked is left as it stands.

`run` is the traced-run verb: with `ws` marked, it appends one `bash`
event to the workspace's draft trace (`authoring.TRACE`, the same shape
`hooks.event`'s own `PostToolUse`/`Bash` case writes) and then actually
runs the command. It returns the child's own exit code unchanged -- never
translated into a different code -- so a session composing commands can
use `run` as a plain predicate (`run(cmd, ws) == 0`).

A *named* producer is a shorthand for the shell command `kernel.rebuild`'s
`producer` argument expects (`_PRODUCERS`): `_expand_producer` resolves a
name to its command and the `producer_env` `kernel.rebuild` forwards past
its environment scrub, built from whichever of `_PRODUCER_PASSTHROUGH`'s
variables the caller's own environment happens to carry. A name `rebuild`
does not recognize passes through unchanged, so a caller may always hand
it a literal shell command instead. `_ensure` preflights a named
producer's own credential -- the one environment variable it cannot run
without -- so a missing key refuses up front, before anything has been
spent on a producer process that was always going to fail.
"""
import os
import subprocess
import time

from .. import _util
from .. import authoring
from .. import hooks
from .. import kernel

_VERSION = "2.0"

_SHELL = "/bin/sh"

# Named producer shortcuts: a shell command, and the environment variable
# (if any) that command cannot run without.
_PRODUCERS = {
    "codex": {"cmd": "codex exec --full-auto --skip-git-repo-check -", "credential": None},
    "openai": {"cmd": "python3 -m reticuli._producers.openai", "credential": "OPENAI_API_KEY"},
}

# Variables a caller's own environment may carry that a named producer is
# deliberately handed past `kernel.rebuild`'s scrub.
_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')


class HandlerError(Exception):
    """A handler's own refusal, with a human reason -- never a bare crash."""


# ------------------------------------------------------------- producer --

def _ensure(name: str) -> None:
    """Preflight a named producer's own credential: refuse before anything
    is spent, not after its process has already failed. A name
    `_PRODUCERS` does not recognize has nothing to preflight."""
    spec = _PRODUCERS.get(name)
    if spec is None:
        return
    credential = spec.get("credential")
    if credential and not os.environ.get(credential):
        raise HandlerError(
            f"producer {name!r} needs {credential} set; refusing before spending")


def _expand_producer(name_or_cmd: str):
    """A producer argument as `kernel.rebuild` wants it: `(cmd, env)` --
    `name_or_cmd`'s own command if `_PRODUCERS` names it (preflighted
    first), `name_or_cmd` itself otherwise; `env` carries whichever of
    `_PRODUCER_PASSTHROUGH`'s variables the caller's environment holds."""
    spec = _PRODUCERS.get(name_or_cmd)
    if spec is not None:
        _ensure(name_or_cmd)
        cmd = spec["cmd"]
    else:
        cmd = name_or_cmd
    env = {k: os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ}
    return cmd, env


# ------------------------------------------------------------- workspace --

def _scan_workspace(ws: str) -> dict:
    """What already exists at `ws`, before `init` decides what to do:
    whether the directory itself, its `.reticuli` mark, a draft trace
    already recording a session, and a sealed claim's manifest are
    present."""
    return {
        "exists": os.path.isdir(ws),
        "marked": os.path.isdir(os.path.join(ws, kernel.STORE)),
        "traced": os.path.isfile(os.path.join(ws, authoring.TRACE)),
        "sealed": os.path.isfile(os.path.join(ws, kernel.MANIFEST)),
    }


def _version_line() -> str:
    """The one-line version banner a `--version` flag prints."""
    return f"reticuli {_VERSION}"


def init(path: str, no_agent: bool = False) -> dict:
    """Mark `path` as a workspace: make the directory and its `.reticuli`
    store if they are not there yet, and -- unless `no_agent` -- wire the
    coding-agent handshake (`hooks.install`) so a traced session can
    begin. Idempotent: a workspace already marked is left as it stands."""
    d = os.path.abspath(path)
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, kernel.STORE), exist_ok=True)

    wired = None
    if not no_agent:
        wired = hooks.install(d)

    name = os.path.basename(d.rstrip(os.sep)) or d
    return {"name": name, "path": d, "wired": wired}


def run(cmd: str, ws: str) -> int:
    """Run `cmd` as a shell command with `ws` as its working directory,
    tracing it into the workspace's draft trace first if `ws` is marked
    (the same `bash` event shape `hooks.event` records); returns the
    child's own exit code unchanged, so a session can use `run` as a
    plain predicate."""
    d = os.path.abspath(ws)
    scan = _scan_workspace(d)
    if scan["marked"]:
        entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
        _util.trace_append(os.path.join(d, authoring.TRACE), entry)
    proc = subprocess.run([_SHELL, "-c", cmd], cwd=d)
    return proc.returncode
