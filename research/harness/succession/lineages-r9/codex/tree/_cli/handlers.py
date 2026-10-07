"""Session setup and execution helpers for the command line."""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import time

from reticuli import kernel


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer carries its credential requirement with its command.
_PRODUCERS = {
    "codex": ("OPENAI_API_KEY", "codex exec"),
    "openai": ("OPENAI_API_KEY", "codex exec"),
}


def _ensure(path):
    """Create a directory if needed and return its absolute path."""
    directory = os.path.abspath(os.fspath(path))
    os.makedirs(directory, exist_ok=True)
    return directory


def _expand_producer(producer, environment=None):
    """Resolve a named producer, checking its credential before invocation."""
    if not isinstance(producer, str) or not producer.strip():
        raise kernel.ClaimError("producer must be a nonempty command or name")
    named = _PRODUCERS.get(producer)
    if named is None:
        return producer
    credential, command = named
    values = os.environ if environment is None else environment
    if not values.get(credential):
        raise kernel.ClaimError(f"{producer} producer requires {credential}")
    return command


def _scan_workspace(workspace):
    """List workspace files, excluding Reticuli's session residue."""
    root = os.path.abspath(os.fspath(workspace))
    if not os.path.isdir(root):
        raise kernel.ClaimError(f"workspace does not exist: {root}")
    found = []
    for parent, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories
                                if name not in (".reticuli", ".git")
                                and not os.path.islink(os.path.join(parent, name)))
        for name in sorted(files):
            path = os.path.join(parent, name)
            if os.path.isfile(path) and not os.path.islink(path):
                found.append(os.path.relpath(path, root))
    return found


def _version_line():
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "development"
    return f"reticuli {version}"


def init(workspace, *, no_agent=False):
    """Mark a workspace for authoring and optionally install agent hooks."""
    root = _ensure(workspace)
    _ensure(os.path.join(root, kernel.STORE))
    if not no_agent:
        from reticuli import hooks

        hooks.install(root)
    return {"status": "ready", "path": root}


def run(command, workspace):
    """Trace a shell command and return its exit status without translation."""
    root = os.path.abspath(os.fspath(workspace))
    if not os.path.isdir(root):
        raise kernel.ClaimError(f"workspace does not exist: {root}")
    if not isinstance(command, str):
        raise kernel.ClaimError("run command must be a string")
    trace = os.path.join(root, kernel.STORE, "draft.jsonl")
    _ensure(os.path.dirname(trace))
    event = {"event": "bash", "cmd": command, "ts": time.time()}
    with open(trace, "a", encoding="utf-8") as target:
        target.write(json.dumps(event, sort_keys=True) + "\n")
    try:
        return subprocess.run(command, shell=True, cwd=root, check=False).returncode
    except OSError as exc:
        raise kernel.ClaimError(f"cannot run command: {exc}") from exc
