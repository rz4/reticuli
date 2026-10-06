"""Small command handlers for starting and recording a local session."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

from reticuli import hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# Named producers are expanded before execution, so callers can supply either
# a registered name or a complete shell command.
_PRODUCERS: dict[str, str] = {}


def _ensure(path: str | os.PathLike[str]) -> str:
    """Create a directory and return its absolute path."""
    directory = os.path.abspath(os.fspath(path))
    os.makedirs(directory, exist_ok=True)
    return directory


def _expand_producer(producer: str) -> str:
    """Expand a registered producer name, preserving custom commands."""
    if not isinstance(producer, str) or not producer.strip():
        raise ValueError("producer must be a nonempty command or name")
    return _PRODUCERS.get(producer, producer)


def _scan_workspace(workspace: str | os.PathLike[str]) -> list[str]:
    """List regular workspace files without including session residue."""
    root = Path(workspace)
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                  if path.is_file() and ".reticuli" not in path.relative_to(root).parts)


def _version_line() -> str:
    """Return the CLI's short version banner."""
    try:
        from importlib.metadata import version
        release = version("reticuli")
    except Exception:
        release = "unknown"
    return f"reticuli {release}"


def init(workspace: str | os.PathLike[str], no_agent: bool = False) -> dict:
    """Mark a workspace as a session and optionally install editor hooks."""
    root = _ensure(workspace)
    _ensure(os.path.join(root, ".reticuli"))
    result = {"ok": True, "workspace": root}
    if not no_agent:
        result["hooks"] = hooks.install(root)
    return result


def run(command: str, workspace: str | os.PathLike[str]) -> int:
    """Run a shell command in the workspace, recording it for authoring."""
    if not isinstance(command, str):
        raise TypeError("command must be a string")
    root = os.path.abspath(os.fspath(workspace))
    if not os.path.isdir(os.path.join(root, ".reticuli")):
        raise ValueError(f"workspace is not initialized: {root}")
    result = subprocess.run(command, shell=True, cwd=root, check=False)
    trace = os.path.join(root, ".reticuli", "draft.jsonl")
    with open(trace, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "bash", "cmd": command,
                                 "ts": time.time()}, sort_keys=True) + "\n")
    return result.returncode
