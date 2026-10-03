"""Workspace and command handlers for the Reticuli CLI."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import time

from reticuli import hooks
from reticuli._util import trace_append


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

_PRODUCERS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


def _ensure(workspace):
    """Create a workspace marker and return its absolute path."""
    path = os.path.abspath(os.fspath(workspace))
    os.makedirs(os.path.join(path, ".reticuli"), exist_ok=True)
    return path


def _scan_workspace(start=None):
    """Find the nearest marked workspace containing *start*."""
    path = os.path.abspath(os.fspath(start or os.getcwd()))
    while True:
        if os.path.isdir(os.path.join(path, ".reticuli")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def _expand_producer(producer):
    """Resolve a named producer, checking its credential before use."""
    if producer not in _PRODUCERS:
        return producer
    missing = [key for key in _PRODUCERS[producer] if not os.environ.get(key)]
    if missing:
        raise ValueError(f"{producer} producer requires {', '.join(missing)}")
    return producer


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "development"
    return f"reticuli {version}"


def init(workspace, *, no_agent=False):
    """Mark a directory as a workspace and optionally install agent hooks."""
    path = _ensure(workspace)
    if not no_agent:
        hooks.install(path)
    return path


def run(command, workspace):
    """Record and execute a shell command, returning its exact exit status."""
    path = _ensure(workspace)
    trace_append(path, {"event": "bash", "cmd": command, "ts": time.time()})
    return subprocess.run(command, shell=True, cwd=path, check=False).returncode
