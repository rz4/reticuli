"""Session setup and command execution for the command line."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time

from .. import hooks
from .._util import trace_append


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer needs its credential before a session can invoke it.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "codex exec"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude -p"),
}


def _ensure(directory):
    """Create a workspace and its session store, returning the workspace path."""
    directory = os.path.abspath(os.fspath(directory))
    os.makedirs(os.path.join(directory, ".reticuli"), exist_ok=True)
    return directory


def _expand_producer(producer):
    """Resolve a named producer and check its credential before use."""
    if producer not in _PRODUCERS:
        return producer
    credential, command = _PRODUCERS[producer]
    if not os.environ.get(credential):
        raise ValueError(f"{producer} producer requires {credential}")
    return command


def _scan_workspace(directory):
    """List the files visible to a session, excluding its residue."""
    names = []
    for base, folders, files in os.walk(directory):
        folders[:] = sorted(name for name in folders if name != ".reticuli")
        for name in files:
            names.append(os.path.relpath(os.path.join(base, name), directory).replace(os.sep, "/"))
    return sorted(names)


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return f"reticuli {version}"


def init(directory, *, no_agent=False):
    """Mark a directory as a traced workspace."""
    directory = _ensure(directory)
    if not no_agent:
        hooks.install(directory)
    return {"path": directory, "trace": os.path.join(directory, hooks.TRACE)}


def run(command, directory):
    """Record a shell command and return its exact process exit status."""
    directory = _ensure(directory)
    trace_append(directory, {"event": "bash", "cmd": command, "ts": time.time()})
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode
