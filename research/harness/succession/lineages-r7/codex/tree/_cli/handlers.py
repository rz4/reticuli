"""Workspace session commands and producer selection for the CLI."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .. import hooks
from .._util import trace_append


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer needs its credential before a rebuild starts.  A shell
# command supplied by the caller remains a shell command, without this lookup.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "openai"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude"),
    "claude": ("ANTHROPIC_API_KEY", "claude"),
}


def _ensure(path):
    """Create a directory and return its absolute path."""
    directory = os.path.abspath(os.fspath(path))
    os.makedirs(directory, exist_ok=True)
    return directory


def _expand_producer(producer):
    """Resolve a known producer name, checking its credential first."""
    if producer not in _PRODUCERS:
        return producer
    credential, command = _PRODUCERS[producer]
    if not os.environ.get(credential):
        raise ValueError(f"{producer} producer requires {credential}")
    return command


def _scan_workspace(workspace):
    """List regular workspace files, excluding session residue."""
    root = Path(workspace)
    if not root.is_dir():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".reticuli" not in path.relative_to(root).parts
    )


def _version_line():
    """Return a short version line for the CLI."""
    try:
        from importlib.metadata import version
        return f"reticuli {version('reticuli')}"
    except Exception:
        return "reticuli"


def init(workspace, no_agent=False):
    """Mark a workspace for tracing and optionally wire agent hooks."""
    root = _ensure(workspace)
    _ensure(os.path.join(root, ".reticuli"))
    if not no_agent:
        hooks.install(root)
    return root


def run(command, workspace):
    """Run a shell command in a workspace, preserving its exit code."""
    root = os.path.abspath(os.fspath(workspace))
    if not os.path.isdir(root):
        raise FileNotFoundError(root)
    if os.path.isdir(os.path.join(root, ".reticuli")):
        trace_append(root, {"event": "bash", "cmd": command, "ts": time.time()})
    return subprocess.run(command, shell=True, cwd=root, check=False).returncode
