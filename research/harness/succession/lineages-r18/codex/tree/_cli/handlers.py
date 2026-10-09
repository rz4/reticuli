"""Workspace setup and the small command handlers used by the CLI."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .. import hooks, kernel


# These variables are deliberately passed to a producer only when requested.
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")
_PRODUCERS = {
    "codex": ("codex exec", "OPENAI_API_KEY"),
    "openai": ("codex exec", "OPENAI_API_KEY"),
    "claude": ("claude -p", "ANTHROPIC_API_KEY"),
}


def _ensure(workspace: os.PathLike[str] | str) -> str:
    """Create the workspace marker and return the workspace's absolute path."""
    path = os.path.abspath(os.fspath(workspace))
    os.makedirs(os.path.join(path, kernel.STORE), exist_ok=True)
    return path


def _expand_producer(producer: str) -> str:
    """Resolve a named producer, checking its credential before invocation."""
    if producer not in _PRODUCERS:
        return producer
    command, credential = _PRODUCERS[producer]
    if not os.environ.get(credential):
        raise kernel.ClaimError(f"{producer} producer needs {credential}")
    return command


def _scan_workspace(workspace: os.PathLike[str] | str) -> dict[str, object]:
    """Summarize the local session marker and any sealed claims."""
    path = os.path.abspath(os.fspath(workspace))
    store = os.path.join(path, kernel.STORE)
    return {"workspace": path, "initialized": os.path.isdir(store),
            "claims": __import__("reticuli.registry", fromlist=["claims"]).claims(path)
            if os.path.isdir(store) else []}


def _version_line() -> str:
    """Return a short diagnostic version line for the command line."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        number = version("reticuli")
    except PackageNotFoundError:
        number = "development"
    return f"reticuli {number}"


def init(workspace: os.PathLike[str] | str = ".", *, no_agent: bool = False) -> dict[str, object]:
    """Mark a directory as a workspace and optionally install agent hooks."""
    path = _ensure(workspace)
    result: dict[str, object] = {"workspace": path, "initialized": True}
    if not no_agent:
        result["hooks"] = hooks.install(path)
    return result


def run(command: str, workspace: os.PathLike[str] | str = ".") -> int:
    """Run a traced shell command, preserving the child's exit status."""
    if not isinstance(command, str):
        raise TypeError("command must be a string")
    path = _ensure(workspace)
    completed = subprocess.run(command, shell=True, cwd=path, check=False)
    trace = Path(path) / kernel.STORE / "draft.jsonl"
    with trace.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"event": "bash", "cmd": command,
                                 "ts": time.time(), "returncode": completed.returncode},
                                sort_keys=True) + "\n")
    return completed.returncode
