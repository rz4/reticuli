"""Small command handlers used by the Reticuli command-line surface.

This module owns the two pieces of session plumbing that should not be
reimplemented by individual parsers: creating a marked workspace and running
(and recording) a command in that workspace.  It also contains the modest
producer-alias expansion seam used by rebuild commands.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import Any

from reticuli import kernel


# Variables deliberately handed to a producer in addition to its credential.
# Keep this an allow-list: the kernel otherwise scrubs the inherited process
# environment before invoking a producer.
_PRODUCER_PASSTHROUGH = (
    "OPENAI_BASE_URL",
    "RETICULI_PRICE",
    "RETICULI_AGENT_TURNS",
)

# Producer aliases are intentionally data rather than branches in
# ``_expand_producer``.  Integrators may add an entry of the form
#
#   name: {"command": "...", "credential": "SOME_API_KEY"}
#
# A string value is also accepted for an alias which needs no credential.
# Reticuli itself does not presume that an external agent executable exists.
_PRODUCERS: dict[str, Any] = {}


def _ensure(value: Any, fact: str | None = None) -> Any:
    """Return *value* when truthy, otherwise raise the canonical refusal.

    If *value* is the name of an environment variable and *fact* is omitted,
    the variable is looked up.  This shorthand is useful for producer
    credential preflight and, importantly, performs the check before a child
    process is started.
    """
    if isinstance(value, str) and fact is None:
        present = os.environ.get(value)
        if present:
            return present
        raise kernel.ClaimError(f"required environment variable is not set: {value}")
    if not value:
        raise kernel.ClaimError(fact or "required value is missing")
    return value


def _expand_producer(producer: Any, environ: Mapping[str, str] | None = None) -> str:
    """Expand a producer alias to a shell command, preflighting credentials.

    Unknown names are ordinary shell commands and are returned unchanged.
    Alias descriptors may be strings, ``(command, credential)`` pairs, or
    mappings with ``command`` and optional ``credential`` members.  Credential
    checks happen here, before the command can spend money or mutate a build.
    """
    if not isinstance(producer, str) or not producer.strip():
        raise kernel.ClaimError("producer must be a non-empty command")

    descriptor = _PRODUCERS.get(producer)
    if descriptor is None:
        return producer

    command: Any
    credential: Any = None
    if isinstance(descriptor, str):
        command = descriptor
    elif isinstance(descriptor, Mapping):
        command = descriptor.get("command")
        credential = descriptor.get("credential")
    elif isinstance(descriptor, (tuple, list)) and descriptor:
        command = descriptor[0]
        credential = descriptor[1] if len(descriptor) > 1 else None
    else:
        raise kernel.ClaimError(f"producer alias is malformed: {producer}")

    command = _ensure(command, f"producer alias has no command: {producer}")
    if credential:
        source = os.environ if environ is None else environ
        _ensure(source.get(str(credential)),
                f"producer credential is not set: {credential}")
    return str(command)


def _scan_workspace(path: Any = ".") -> str | None:
    """Find the nearest enclosing directory marked by ``.reticuli``.

    ``None`` is returned when no session marker is found.  The function does
    not change the process working directory and accepts either a file or a
    directory as its starting point.
    """
    try:
        current = os.path.abspath(os.fspath(path))
    except (TypeError, ValueError, OSError):
        return None
    if not os.path.isdir(current):
        current = os.path.dirname(current)
    while True:
        if os.path.isdir(os.path.join(current, kernel.STORE)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _version_line() -> str:
    """Return a printable Reticuli version line without requiring packaging."""
    try:
        version = importlib.metadata.version("reticuli")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return f"reticuli {version}"


def init(path: Any = ".", *, no_agent: bool = False) -> dict[str, Any]:
    """Create (or mark) an authoring workspace.

    Existing project files are left untouched.  Unless ``no_agent`` is true,
    Claude-compatible hooks are installed in the project settings; hook setup
    is deliberately performed only after the workspace marker exists.
    """
    try:
        workspace = os.path.abspath(os.fspath(path))
    except (TypeError, ValueError, OSError) as exc:
        raise kernel.ClaimError(f"invalid workspace path: {exc}") from None

    if os.path.exists(workspace) and not os.path.isdir(workspace):
        raise kernel.ClaimError("workspace path is not a directory")
    os.makedirs(os.path.join(workspace, kernel.STORE), exist_ok=True)

    result: dict[str, Any] = {
        "ok": True,
        "status": "initialized",
        "path": workspace,
        "name": os.path.basename(workspace),
    }
    if not no_agent:
        from reticuli import hooks
        try:
            result["hooks"] = hooks.install(workspace)
        except (OSError, ValueError, TypeError) as exc:
            # A usable session does not depend on one editor's settings.  The
            # diagnostic remains available to a caller without undoing init.
            result["hooks"] = {"status": "not wired", "error": str(exc)}
    return result


def _trace(workspace: str, command: str) -> None:
    """Append one command event to a session trace."""
    store = os.path.join(workspace, kernel.STORE)
    os.makedirs(store, exist_ok=True)
    path = os.path.join(store, "draft.jsonl")
    item = {"event": "bash", "cmd": command, "ts": time.time()}
    line = json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
    except OSError as exc:
        raise kernel.ClaimError(f"cannot write session trace: {exc}") from None


def run(command: Any, workspace: Any = ".") -> int:
    """Trace and execute *command* in *workspace*.

    The shell child's return code is returned unchanged.  In particular this
    handler does not turn every non-zero result into the CLI's generic status
    code; callers may use a session command as a predicate.
    """
    if not isinstance(command, str) or not command:
        raise kernel.ClaimError("run command must be a non-empty string")
    try:
        directory = os.path.abspath(os.fspath(workspace))
    except (TypeError, ValueError, OSError) as exc:
        raise kernel.ClaimError(f"invalid workspace path: {exc}") from None
    if not os.path.isdir(directory):
        raise kernel.ClaimError("workspace is not a directory")
    if not os.path.isdir(os.path.join(directory, kernel.STORE)):
        raise kernel.ClaimError("workspace is not initialized")

    _trace(directory, command)
    try:
        completed = subprocess.run(command, cwd=directory, shell=True,
                                   check=False)
    except OSError as exc:
        raise kernel.ClaimError(f"cannot run session command: {exc}") from None
    return int(completed.returncode)


__all__ = [
    "_PRODUCER_PASSTHROUGH", "_PRODUCERS", "_ensure",
    "_expand_producer", "_scan_workspace", "_version_line", "init", "run",
]
