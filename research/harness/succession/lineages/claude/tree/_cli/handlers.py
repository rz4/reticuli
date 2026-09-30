"""reticuli._cli.handlers -- session setup, traced run, producer preflight.

`init` marks a workspace as a reticuli session: it creates the workspace
and its `.reticuli` store, and -- unless `no_agent` -- wires the coding-
agent hooks (`reticuli.hooks.install`, `spec/layers.md`'s agents layer) so
a session's prompts and tool calls are traced automatically. `run`
executes one shell command scoped to the session, traces it, and returns
the child's exit code unchanged, so a session script can use it as a
predicate (`ret run "pytest" && ret seal`).

A **named producer** is a shorthand for a full producer command: a
handful of vendors this tool talks to out of the box (`_PRODUCERS`), each
name expanding (`_expand_producer`) to its invocation only after
preflighting (`_ensure`) the one credential it needs -- so a misconfigured
session refuses before it spends anything, not partway through a rebuild.
Anything not a known name is already a shell command and passes through
unchanged. `_PRODUCER_PASSTHROUGH` lists the environment variables let
through to a producer's child process untouched, on top of the scrubbed
allowlist every gate already runs under (`spec/claim-format.md`).

Stdlib only. Never the network.
"""
import os
import platform
import subprocess
import sys

from .. import _util
from .. import hooks as _hooks
from .. import kernel

_PRODUCER_PASSTHROUGH = ('OPENAI_BASE_URL', 'RETICULI_PRICE', 'RETICULI_AGENT_TURNS')

_PRODUCERS = {
    "openai": {"credential": "OPENAI_API_KEY", "cmd": "codex exec --full-auto"},
    "anthropic": {"credential": "ANTHROPIC_API_KEY", "cmd": "claude -p --dangerously-skip-permissions"},
}


def _ensure(condition, message: str) -> None:
    """Refuse, in words, unless `condition` -- the one place this module
    raises rather than letting a bare crash speak for it."""
    if not condition:
        raise kernel.ClaimError(message)


def _expand_producer(spec: str) -> str:
    """`spec` as the shell command a rebuild should run. A name in
    `_PRODUCERS` preflights its one credential (raising if it is missing
    from the environment) and expands to that producer's invocation;
    anything else is already a shell command and passes through
    unchanged."""
    producer = _PRODUCERS.get(spec)
    if producer is None:
        return spec
    credential = producer["credential"]
    _ensure(os.environ.get(credential), f"missing credential: set {credential} to use {spec!r}")
    return producer["cmd"]


def _scan_workspace(ws: str) -> list:
    """One entry per claim sealed in `ws`'s store: `{name, root}`, read
    straight off `.reticuli/sealed/` without going through the exchange
    layer -- a malformed or half-written entry is skipped, not raised."""
    sealed = os.path.join(ws, kernel.STORE, "sealed")
    rows = []
    if not os.path.isdir(sealed):
        return rows
    for entry in sorted(os.listdir(sealed)):
        comp_dir = os.path.join(sealed, entry)
        if not os.path.isdir(comp_dir):
            continue
        try:
            manifest = kernel.read_manifest(comp_dir)
        except kernel.ClaimError:
            continue
        rows.append({"name": manifest.get("name"), "root": manifest.get("root")})
    return rows


def _version_line() -> str:
    """One line naming this tool and the interpreter running it -- the
    `tool` a record stamps (`spec/record.md`) and what `ret --version`
    prints."""
    runtime = f"{platform.python_implementation()} {platform.python_version()}"
    return f"reticuli ({runtime} on {sys.platform})"


def init(ws: str, no_agent: bool = False) -> dict:
    """Mark `ws` as a reticuli session: create it and its `.reticuli`
    store, and -- unless `no_agent` -- wire the coding-agent hooks so the
    session's prompts and tool calls are traced automatically."""
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    data = {"claim": ws}
    if not no_agent:
        data["hooks"] = _hooks.install(ws)
    return data


def run(cmd: str, ws: str) -> int:
    """Run `cmd` in a shell scoped to `ws`, trace it into the session's
    trace log, and return the child's exit code unchanged -- so a session
    script can use it as a predicate."""
    done = subprocess.run(cmd, shell=True, cwd=ws)
    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        _util.trace_append(ws, {"event": "run", "cmd": cmd, "exit": done.returncode})
    return done.returncode
