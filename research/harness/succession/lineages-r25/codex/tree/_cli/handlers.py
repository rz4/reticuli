"""Session setup and command execution for the command line."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path

from .. import authoring, hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer needs its credential before a rebuild starts.  Shell
# commands supplied explicitly by the caller have no implied credential.
_PRODUCERS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _ensure(directory):
    """Create a workspace and its local trace store, returning its path."""
    directory = os.path.abspath(os.fspath(directory))
    os.makedirs(os.path.join(directory, ".reticuli"), exist_ok=True)
    return directory


def _scan_workspace(directory):
    """List ordinary workspace files, excluding local Reticuli residue."""
    base = Path(directory)
    if not base.is_dir():
        return []
    return sorted(path.relative_to(base).as_posix() for path in base.rglob("*")
                  if path.is_file() and not path.is_symlink()
                  and ".reticuli" not in path.relative_to(base).parts)


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "development"
    return f"reticuli {version}"


def _expand_producer(producer, env=None):
    """Validate a named producer's credential and return its shell command."""
    environment = os.environ if env is None else env
    credential = _PRODUCERS.get(producer)
    if credential and not environment.get(credential):
        raise ValueError(f"{producer} producer requires {credential}")
    return producer


def init(directory, *, no_agent=False):
    """Mark a directory as an authoring workspace."""
    directory = _ensure(directory)
    if not no_agent:
        hooks.install(directory)
    return {"status": "ready", "path": directory}


def run(command, directory):
    """Execute a shell command in the workspace and return its exact status."""
    directory = _ensure(directory)
    row = {"event": "bash", "cmd": command, "ts": time.time()}
    with open(os.path.join(directory, authoring.TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode
