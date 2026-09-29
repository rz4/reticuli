"""Session setup and command execution for the command line interface."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from reticuli import hooks
from reticuli.authoring import TRACE


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer must have its credential before it is invoked. An explicit
# shell command remains available for locally installed or offline producers.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "codex"),
    "codex": ("OPENAI_API_KEY", "codex"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude"),
    "claude": ("ANTHROPIC_API_KEY", "claude"),
}


def _ensure(path):
    """Create a directory if necessary and return its path."""
    path = os.fspath(path)
    os.makedirs(path, exist_ok=True)
    return path


def _expand_producer(producer):
    """Resolve a named producer after checking its credential and executable."""
    if producer not in _PRODUCERS:
        return producer
    credential, command = _PRODUCERS[producer]
    if not os.environ.get(credential):
        raise ValueError(f"{producer} requires {credential}")
    if shutil.which(command) is None:
        raise ValueError(f"{producer} requires the {command} executable")
    return command


def _scan_workspace(workspace):
    """Return the regular files in a workspace, excluding session residue."""
    workspace = os.fspath(workspace)
    found = []
    for base, directories, files in os.walk(workspace):
        directories[:] = sorted(d for d in directories if d != ".reticuli")
        for name in sorted(files):
            path = os.path.join(base, name)
            if os.path.isfile(path) and not os.path.islink(path):
                found.append(os.path.relpath(path, workspace))
    return sorted(found)


def _version_line(command):
    """Read the first line of a command's version output, if available."""
    try:
        result = subprocess.run([command, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (result.stdout or result.stderr).splitlines()
    return lines[0].strip() if lines else None


def init(workspace, no_agent=False):
    """Mark a workspace as a traceable authoring session."""
    workspace = os.path.abspath(os.fspath(workspace))
    _ensure(workspace)
    _ensure(os.path.join(workspace, ".reticuli"))
    Path(workspace, TRACE).touch(exist_ok=True)
    if not no_agent:
        hooks.install(workspace)
    return {"ok": True, "path": workspace}


def run(command, workspace):
    """Execute a shell command in a session and return its exact exit code."""
    workspace = os.path.abspath(os.fspath(workspace))
    if not os.path.isdir(os.path.join(workspace, ".reticuli")):
        raise ValueError("workspace has no Reticuli session; run init first")
    if not isinstance(command, str) or not command:
        raise ValueError("command must be nonempty text")
    row = {"event": "bash", "cmd": command, "ts": time.time()}
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as trace:
        trace.write(json.dumps(row, sort_keys=True) + "\n")
    return subprocess.call(command, cwd=workspace, shell=True)
