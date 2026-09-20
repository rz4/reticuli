"""ret command line — the handlers layer: session setup, the traced run, producer preflight, the version line."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from .. import _util, kernel
from .. import authoring as authoring_mod
from .. import hooks as hooks_mod
from ..render import short

# -- session setup (git-native) ---------------------------------------------


def _ensure(path: str, lines: list[str], made: list, label: str) -> None:
    content = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            content = f.read()
    missing = [ln for ln in lines if ln not in content]
    if missing:
        with open(path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("\n".join(missing) + "\n")
        made.append({"path": label, "status": "updated" if content else "created"})




def init(project: str, agent: str | None = None, no_agent: bool = False) -> dict:
    root = os.path.abspath(project)
    made: list = []
    os.makedirs(os.path.join(root, kernel.STORE), exist_ok=True)
    trace = os.path.join(root, authoring_mod.TRACE)
    rel = authoring_mod.TRACE.replace(os.sep, "/")   # git patterns are posix
    if not os.path.exists(trace):
        open(trace, "w").close()
        made.append({"path": rel, "status": "created"})
    _ensure(os.path.join(root, ".gitignore"),
            ["# Reticuli: history is local — never committed",
             rel, ".reticuli/**/ledger.jsonl",
             ".reticuli/**/tmp/"], made, ".gitignore")
    _ensure(os.path.join(root, ".gitattributes"),
            ["# Reticuli: sealed bytes are binary — no text/CRLF conversion",
             ".reticuli/** -text"], made, ".gitattributes")
    # Agent integration is part of starting, not a separate concept. The Claude
    # Code harness is auto-wired (detected, or asked for); any other harness is
    # `--agent generic`: the workspace is set up and the harness is pointed at
    # the generic `ret hook` contract, since reticuli cannot know its config.
    wiring = None
    agent_name = None
    if agent and agent not in ("claude", "generic"):
        raise kernel.ClaimError(
            f"init: unsupported agent {agent!r} (supported: claude, generic)")
    if no_agent:
        pass
    elif agent == "generic":
        agent_name = "generic"           # workspace ready; harness targets `ret hook`
    elif agent == "claude" or (agent is None
                               and os.path.isdir(os.path.join(root, ".claude"))):
        wiring = hooks_mod.install(root)
        agent_name = "claude"
    return {"project": root, "files": made, "agent": agent_name,
            "agent_wiring": wiring, "hook_command": hooks_mod._hook_command()}




def _scan_workspace(root: str) -> dict[str, str]:
    """Every real project file under root, path -> content hash. Excludes the
    reticuli store, hidden entries, and Python bytecode -- the same set the
    trace and feedback already treat as the project. A `ret run` scans before
    and after so a command's file effects are captured even when no editor hook
    saw them: content, not mtime, so a rewrite to identical bytes counts as no
    change and a real change is never missed."""
    scan: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            if name.startswith(".") or name.endswith((".pyc", ".pyo")):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as fh:
                    scan[rel] = _util.hash_bytes(fh.read())
            except OSError:
                continue
    return scan




def run(cmd: str, workspace: str) -> int:
    """A silent wrapper: only the child's streams. The trace records the command
    and the file effects it left -- a before/after content scan of the
    workspace, so work a script or subprocess does is captured even though no
    editor hook saw it. Reads cannot be derived from a content diff, so they
    stay unobserved; the honest-pack warnings say what could not be seen."""
    root = os.path.abspath(workspace)
    trace = os.path.join(root, authoring_mod.TRACE)
    os.makedirs(os.path.dirname(trace), exist_ok=True)
    before = _scan_workspace(root)
    proc = subprocess.run(cmd, shell=True, cwd=root, check=False,
                          env={**os.environ, "RETICULI": "1"})
    after = _scan_workspace(root)
    touched = sorted(rel for rel, h in after.items() if before.get(rel) != h)
    # Stamped and lock-serialized: a swarm of agents and subprocesses appends to
    # this one trace at once, and each event is grouped by its run (see _util).
    _util.trace_append(trace, {"event": "bash", "cmd": cmd, "via": "shell",
                               "rc": proc.returncode})
    for rel in touched:
        _util.trace_append(trace, {"event": "write", "path": rel, "via": "shell"})
    return proc.returncode




#: The shipped producers, addressable by name: `--producer openai[:model]`.
#: Naming one IS the authorization to hand it its own vendor's credential —
#: only the matched key, only for shipped names, never to gates, and never
#: for a raw command (which keeps the do-it-yourself contract unchanged).
_PRODUCERS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE",
                         "RETICULI_AGENT_TURNS")




def _expand_producer(spec: str):
    """A shipped producer's name becomes its full invocation; anything else
    passes through verbatim. Returns (command, env) — env is what the user's
    naming authorizes us to hand the producer over the scrub.

    Preflight refuses BEFORE any money moves: a missing SDK or credential is
    a one-line answer here, not a traceback from inside the room."""
    import importlib.util
    import re as _re
    import shlex
    m = _re.fullmatch(r"(openai|anthropic)(?::([\w.\-]+))?", spec)
    if not m:
        return spec, None
    name, model = m.groups()
    needs = []
    if importlib.util.find_spec(name) is None:
        needs.append(f"the {name} package (pip install {name})")
    key_var = _PRODUCERS[name]
    if not os.environ.get(key_var):
        needs.append(f"{key_var} in your environment")
    if needs:
        raise kernel.ClaimError(
            f"rebuild: the {name} producer needs: " + "; ".join(needs))
    env = {key_var: os.environ[key_var]}
    for var in _PRODUCER_PASSTHROUGH:
        if os.environ.get(var):
            env[var] = os.environ[var]
    if model:
        env["RETICULI_MODEL"] = model
        os.environ.setdefault("RETICULI_MODEL", model)   # the judge's ledger
    os.environ.setdefault("RETICULI_VENDOR", name)
    # our own package's parent rides PYTHONPATH, and -P keeps the room's
    # files from shadowing it — the producer must import THIS reticuli
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(
        os.path.abspath(kernel.__file__)))
    command = f"{shlex.quote(sys.executable)} -P -m reticuli.producers.{name}"
    return command, env




def _version_line() -> str:
    try:
        from importlib import metadata
        version = metadata.version("reticuli")
    except (ImportError, OSError, metadata.PackageNotFoundError):
        version = "unversioned"
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    try:
        with open(os.path.join(repo, kernel.MANIFEST), encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("name") == "reticuli" and manifest.get("root"):
            return f"ret {version} (root {short(manifest['root'])})"
    except (OSError, ValueError):
        pass
    return f"ret {version}"
