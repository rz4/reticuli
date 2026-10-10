"""Workspace setup and shell command handlers for the command line."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time

from .. import hooks


_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "codex exec"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude -p"),
}


def _ensure(directory):
    """Return an initialized workspace, creating its trace store if needed."""
    directory = os.path.realpath(os.fspath(directory))
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
    """List ordinary workspace files, excluding the session store."""
    directory = os.path.realpath(os.fspath(directory))
    found = []
    for base, dirs, files in os.walk(directory):
        dirs[:] = sorted(name for name in dirs if name != ".reticuli")
        for name in sorted(files):
            found.append(os.path.relpath(os.path.join(base, name), directory))
    return sorted(found)


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return f"reticuli {version}"


def init(directory, *, no_agent=False):
    """Mark a directory as a workspace and optionally install session hooks."""
    directory = _ensure(directory)
    if not no_agent:
        hooks.install(directory)
    return {"path": directory, "status": "initialized"}


def run(command, directory):
    """Run a shell command in the workspace and record its exit status."""
    directory = _ensure(directory)
    if not isinstance(command, str):
        raise TypeError("command must be a string")
    result = subprocess.run(command, shell=True, cwd=directory, check=False)
    trace = os.path.join(directory, hooks.TRACE)
    with open(trace, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "bash", "cmd": command,
                                 "code": result.returncode, "ts": time.time()},
                                sort_keys=True) + "\n")
    return result.returncode
