"""Workspace setup and traced command execution for the command line."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path

from reticuli import hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# A named producer has a credential requirement. An arbitrary shell command
# remains available for producers managed by the caller.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "codex exec"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude -p"),
}


def _ensure(workspace):
    """Create the workspace and its local, unsealed session store."""
    directory = Path(workspace).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".reticuli").mkdir(exist_ok=True)
    return str(directory)


def _scan_workspace(workspace):
    """List ordinary workspace files without including session residue."""
    directory = Path(workspace).expanduser().resolve()
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and ".reticuli" not in path.relative_to(directory).parts
    )


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "development"
    return f"reticuli {version}"


def _expand_producer(producer):
    """Resolve a named producer after checking its required credential."""
    if producer in _PRODUCERS:
        credential, command = _PRODUCERS[producer]
        if not os.environ.get(credential):
            raise ValueError(f"{producer} producer requires {credential}")
        return command
    return producer


def init(workspace, no_agent=False):
    directory = _ensure(workspace)
    if not no_agent:
        hooks.install(directory)
    return {"ok": True, "workspace": directory}


def run(command, workspace):
    """Run a shell command in a workspace and return its exact exit status."""
    directory = _ensure(workspace)
    event = {"event": "bash", "cmd": command, "ts": time.time()}
    with open(os.path.join(directory, hooks.TRACE), "a", encoding="utf-8") as trace:
        trace.write(json.dumps(event, sort_keys=True) + "\n")
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode
