"""Session setup and command execution for the human-facing CLI."""

from __future__ import annotations

import json
import os
import subprocess
import time
from importlib import metadata
from pathlib import Path

from reticuli import hooks, kernel


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# A named producer is a convenience command with an explicit credential
# requirement. Shell commands supplied by the caller have no such requirement.
_PRODUCERS = {
    "codex": ("codex exec", "OPENAI_API_KEY"),
    "claude": ("claude -p", "ANTHROPIC_API_KEY"),
    "gemini": ("gemini -p", "GEMINI_API_KEY"),
}


def _ensure(directory: str | os.PathLike[str]) -> Path:
    """Create a workspace and its session store; return its absolute path."""
    workspace = Path(directory).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / kernel.STORE).mkdir(exist_ok=True)
    return workspace


def _expand_producer(command: str) -> str:
    """Resolve a named producer after checking its required credential."""
    if command not in _PRODUCERS:
        return command
    expanded, credential = _PRODUCERS[command]
    if not os.environ.get(credential):
        raise kernel.ClaimError(f"{command} requires {credential}")
    return expanded


def _scan_workspace(directory: str | os.PathLike[str]) -> list[str]:
    """List ordinary workspace files, excluding Reticuli and VCS residue."""
    workspace = Path(directory)
    names: list[str] = []
    for base, directories, files in os.walk(workspace):
        directories[:] = sorted(name for name in directories
                                if name not in (kernel.STORE, ".git"))
        for name in sorted(files):
            path = Path(base) / name
            if path.is_file() and not path.is_symlink():
                names.append(path.relative_to(workspace).as_posix())
    return names


def _version_line() -> str:
    try:
        version = metadata.version("reticuli")
    except metadata.PackageNotFoundError:
        version = "development"
    return f"reticuli {version}"


def init(directory: str | os.PathLike[str], *, no_agent: bool = False) -> dict:
    """Mark a workspace for tracing, optionally installing coding-agent hooks."""
    workspace = _ensure(directory)
    result = {"ok": True, "path": str(workspace), "status": "initialized"}
    if not no_agent:
        result["hooks"] = hooks.install(workspace)
    return result


def run(command: str, directory: str | os.PathLike[str]) -> int:
    """Trace and run a shell command, returning its exit code unchanged."""
    workspace = _ensure(directory)
    expanded = _expand_producer(command)
    with (workspace / hooks.TRACE).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": "bash", "cmd": command,
                                 "ts": time.time()}, sort_keys=True) + "\n")
    return subprocess.run(expanded, shell=True, cwd=workspace, check=False).returncode
