"""Handlers for starting and tracing a local authoring session."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer must have its credential before it can be invoked.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


def _ensure(workspace):
    """Create the session store and return its path."""
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    store = root / ".reticuli"
    store.mkdir(exist_ok=True)
    return store


def _expand_producer(producer, environ=None):
    """Resolve a named producer after checking its credential."""
    if producer is None:
        return None
    env = os.environ if environ is None else environ
    required = _PRODUCERS.get(producer)
    if required:
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ValueError("producer %s needs %s" % (producer, ", ".join(missing)))
    return producer


def _scan_workspace(workspace):
    """List workspace files without session residue."""
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                  if path.is_file() and ".reticuli" not in path.relative_to(root).parts)


def _version_line():
    """Return a printable command version."""
    try:
        from importlib.metadata import version
        return "reticuli " + version("reticuli")
    except Exception:
        return "reticuli"


def init(workspace=".", *, no_agent=False, producer=None):
    """Mark a directory as a workspace for traced commands."""
    if not no_agent and producer is not None:
        _expand_producer(producer)
    store = _ensure(workspace)
    (store / "draft.jsonl").touch(exist_ok=True)
    return str(store)


def run(command, workspace=".", *, producer=None):
    """Run a shell command, trace it, and preserve its exit status."""
    if producer is not None:
        _expand_producer(producer)
    store = _ensure(workspace)
    root = store.parent
    started = time.time()
    completed = subprocess.run(command, shell=True, cwd=root, check=False)
    event = {"event": "bash", "cmd": command, "ts": started,
             "returncode": completed.returncode}
    with (store / "draft.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    return completed.returncode
