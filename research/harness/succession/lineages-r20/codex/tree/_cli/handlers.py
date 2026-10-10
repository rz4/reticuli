"""Command line actions for starting and tracing a draft session."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .. import hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# A named producer must have its credential before a rebuild begins.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


def _ensure(workspace):
    """Create a workspace and its draft-session store; return its path."""
    directory = Path(workspace).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".reticuli").mkdir(exist_ok=True)
    return str(directory)


def _expand_producer(producer, env=None):
    """Check credentials for a named producer and return its command."""
    if producer not in _PRODUCERS:
        return producer
    environment = os.environ if env is None else env
    missing = [name for name in _PRODUCERS[producer] if not environment.get(name)]
    if missing:
        raise ValueError("missing producer credential: " + ", ".join(missing))
    return producer


def _scan_workspace(workspace):
    """List regular workspace files, excluding Reticuli's session residue."""
    root = Path(workspace)
    if not root.is_dir():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob("*")
                  if path.is_file() and ".reticuli" not in path.relative_to(root).parts)


def _version_line():
    return "reticuli"


def init(workspace, no_agent=False):
    """Mark a workspace for traced sessions."""
    directory = _ensure(workspace)
    if not no_agent:
        hooks.install(directory)
    return directory


def run(command, workspace):
    """Run a shell command in a session and preserve its exact exit code."""
    directory = _ensure(workspace)
    with open(Path(directory) / hooks.TRACE, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "bash", "cmd": command,
                                 "ts": time.time()}, sort_keys=True) + "\n")
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode
