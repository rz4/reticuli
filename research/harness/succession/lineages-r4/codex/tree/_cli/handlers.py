"""Workspace and command handlers for the command-line interface."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .. import hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer has a command and a credential to check before it runs.
_PRODUCERS = {
    "openai": ("openai", "OPENAI_API_KEY"),
    "anthropic": ("claude", "ANTHROPIC_API_KEY"),
}


def _ensure(directory):
    """Create a workspace and its session store, returning its absolute path."""
    path = os.path.abspath(os.fspath(directory))
    os.makedirs(os.path.join(path, ".reticuli"), exist_ok=True)
    return path


def _scan_workspace(directory):
    """List ordinary workspace files, leaving Reticuli residue out."""
    base = Path(directory)
    return sorted(str(path.relative_to(base)) for path in base.rglob("*")
                  if path.is_file() and ".reticuli" not in path.relative_to(base).parts)


def _version_line():
    """Return the installed package version when one is available."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return "reticuli " + version("reticuli")
    except PackageNotFoundError:
        return "reticuli (source)"


def _expand_producer(producer, environment=None):
    """Resolve a named producer and check its credential before invocation."""
    if producer not in _PRODUCERS:
        return producer
    command, credential = _PRODUCERS[producer]
    env = os.environ if environment is None else environment
    if not env.get(credential):
        raise ValueError(f"{producer} producer requires {credential}")
    return command


def init(directory, *, no_agent=False):
    """Start a traceable authoring session in *directory*."""
    path = _ensure(directory)
    agent = None if no_agent else hooks.install(path)
    return {"path": path, "trace": os.path.join(path, hooks.TRACE), "agent": agent}


def run(command, directory):
    """Trace and execute a shell command, preserving its exit status."""
    path = os.path.abspath(os.fspath(directory))
    if not os.path.isdir(os.path.join(path, ".reticuli")):
        raise ValueError(f"not an initialized workspace: {path}")
    trace = os.path.join(path, hooks.TRACE)
    with open(trace, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "bash", "cmd": command,
                                 "ts": time.time()}, sort_keys=True) + "\n")
    return subprocess.run(command, shell=True, cwd=path, check=False).returncode
