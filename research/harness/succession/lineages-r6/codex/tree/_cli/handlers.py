"""Workspace setup and traced shell commands for the command line."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")
_PRODUCERS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "codex": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _ensure(workspace: os.PathLike[str] | str) -> Path:
    """Create a workspace and its private session directory."""
    directory = Path(workspace).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".reticuli").mkdir(exist_ok=True)
    return directory


def _version_line(program: str) -> str | None:
    """Return the first line of a tool's version report when available."""
    try:
        result = subprocess.run([program, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (result.stdout or result.stderr).splitlines()
    return lines[0] if lines else None


def _expand_producer(producer: str | None) -> str | None:
    """Resolve a named producer after checking its required credential."""
    if not producer:
        return None
    credential = _PRODUCERS.get(producer)
    if credential and not os.environ.get(credential):
        raise ValueError(f"{producer} producer requires {credential}")
    if credential and shutil.which(producer) is None:
        raise ValueError(f"{producer} producer is not installed")
    return producer


def _scan_workspace(workspace: os.PathLike[str] | str) -> dict[str, int]:
    """Snapshot regular file modification times for a session trace."""
    directory = Path(workspace).expanduser().resolve()
    found: dict[str, int] = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d != ".reticuli")
        for name in sorted(files):
            path = Path(root) / name
            if path.is_file() and not path.is_symlink():
                found[path.relative_to(directory).as_posix()] = path.stat().st_mtime_ns
    return found


def _append_trace(workspace: Path, event: dict[str, Any]) -> None:
    with (workspace / ".reticuli" / "draft.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def init(workspace: os.PathLike[str] | str = ".", *, no_agent: bool = False) -> dict[str, str]:
    """Mark a directory as a Reticuli workspace."""
    directory = _ensure(workspace)
    trace = directory / ".reticuli" / "draft.jsonl"
    trace.touch(exist_ok=True)
    return {"path": str(directory), "workspace": str(directory), "status": "ok"}


def run(command: str, workspace: os.PathLike[str] | str = ".",
        *, producer: str | None = None) -> int:
    """Run a shell command in a workspace and return its exact exit status."""
    directory = _ensure(workspace)
    _expand_producer(producer)
    before = _scan_workspace(directory)
    started = time.time()
    try:
        result = subprocess.run(command, shell=True, cwd=directory, check=False)
    finally:
        after = _scan_workspace(directory)
        for path in sorted(after.keys() - before.keys() | {
                name for name in after.keys() & before.keys() if after[name] != before[name]}):
            _append_trace(directory, {"event": "write", "path": path, "ts": time.time()})
    _append_trace(directory, {"event": "bash", "cmd": command,
                              "returncode": result.returncode, "ts": started})
    return result.returncode
