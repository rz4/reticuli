"""Command line actions for starting and recording an authoring session."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from reticuli import hooks


_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS"
)

# A named producer has a command and, optionally, a credential to check before
# a potentially costly rebuild starts. Callers can also supply a shell command.
_PRODUCERS = {
    "codex": ("codex exec", "OPENAI_API_KEY"),
    "openai": ("codex exec", "OPENAI_API_KEY"),
    "claude": ("claude -p", "ANTHROPIC_API_KEY"),
}


def _ensure(program: str) -> str:
    """Return an executable's path, or explain why it cannot be run."""
    found = shutil.which(program)
    if found is None:
        raise RuntimeError(f"required executable is unavailable: {program}")
    return found


def _expand_producer(producer: str) -> str:
    """Expand a named producer after checking its executable and credential."""
    if producer not in _PRODUCERS:
        return producer
    command, credential = _PRODUCERS[producer]
    _ensure(command.split()[0])
    if credential and not os.environ.get(credential):
        raise RuntimeError(f"{producer} needs {credential}")
    return command


def _scan_workspace(directory: str | os.PathLike[str]) -> list[str]:
    """List ordinary workspace files without recording private session data."""
    root = Path(directory)
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".reticuli" not in path.relative_to(root).parts
    )


def _version_line() -> str:
    return "reticuli"


def init(directory: str | os.PathLike[str], *, no_agent: bool = False) -> dict:
    """Mark a workspace for a traced authoring session."""
    root = Path(directory).absolute()
    (root / ".reticuli").mkdir(parents=True, exist_ok=True)
    if not no_agent:
        hooks.install(root)
    return {"path": str(root), "initialized": True}


def run(command: str, directory: str | os.PathLike[str]) -> int:
    """Run a shell command in the workspace and record its observed exit code."""
    root = Path(directory).absolute()
    (root / ".reticuli").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, shell=True, cwd=root, check=False)
    event = {"event": "bash", "cmd": command, "code": completed.returncode,
             "ts": time.time()}
    with (root / ".reticuli" / "draft.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    return completed.returncode
