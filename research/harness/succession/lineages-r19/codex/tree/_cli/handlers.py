"""Workspace setup and traced command execution for the CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from reticuli import _util


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# A named producer must have its credential before a rebuild starts.
_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", "codex exec"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude -p"),
}


def _ensure(variable: str) -> str:
    """Return a required environment value, or explain what is missing."""
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"{variable} is required for this producer")
    return value


def _expand_producer(producer: str) -> str:
    """Resolve a named producer after checking its credential."""
    if producer in _PRODUCERS:
        credential, command = _PRODUCERS[producer]
        _ensure(credential)
        return command
    return producer


def _scan_workspace(workspace: os.PathLike[str] | str) -> list[str]:
    """List ordinary workspace files relative to its root."""
    root = Path(workspace)
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".reticuli" not in path.relative_to(root).parts
    )


def _version_line() -> str:
    """Return a short CLI version line."""
    try:
        from importlib.metadata import version

        return f"reticuli {version('reticuli')}"
    except Exception:
        return "reticuli (source checkout)"


def init(workspace: os.PathLike[str] | str, *, no_agent: bool = False) -> int:
    """Create a workspace and its trace store."""
    root = Path(workspace)
    (root / ".reticuli").mkdir(parents=True, exist_ok=True)
    return 0


def run(command: str, workspace: os.PathLike[str] | str) -> int:
    """Run a shell command in the workspace, recording its exact exit code."""
    root = Path(workspace)
    if not (root / ".reticuli").is_dir():
        raise ValueError(f"workspace is not initialized: {root}")
    result = subprocess.run(command, shell=True, cwd=root, check=False)
    _util.trace_append(os.fspath(root), {
        "event": "run",
        "command": command,
        "returncode": result.returncode,
        "when": _util.stamp(),
    })
    return result.returncode
