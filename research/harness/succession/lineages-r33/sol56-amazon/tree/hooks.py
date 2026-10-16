"""Claude Code hooks for recording an authoring session.

Supported payloads become JSON-lines events in ``.reticuli/draft.jsonl``.
Directories without a Reticuli store are not sessions, and file operations
outside the workspace are ignored.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from typing import Any

TRACE = os.path.join(".reticuli", "draft.jsonl")
_COMMAND = "python3 -m reticuli.hooks"
_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _workspace(payload: Mapping[str, Any]) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, (str, os.PathLike)):
        return None
    try:
        root = os.path.abspath(os.fspath(cwd))
    except (TypeError, ValueError, OSError):
        return None
    if not os.path.isdir(root) or not os.path.isdir(os.path.join(root, ".reticuli")):
        return None
    return root


def _relative_file(root: str, value: Any) -> str | None:
    """Confine a tool file name to *root* and return portable spelling."""
    if not isinstance(value, (str, os.PathLike)):
        return None
    try:
        name = os.fspath(value)
        if not isinstance(name, str) or not name or "\0" in name:
            return None
        path = os.path.abspath(name if os.path.isabs(name) else os.path.join(root, name))
        real_root, real_path = os.path.realpath(root), os.path.realpath(path)
        if os.path.commonpath((real_root, real_path)) != real_root or real_path == real_root:
            return None
        relative = os.path.relpath(path, root)
        if relative == os.pardir or relative.startswith(os.pardir + os.sep):
            return None
        return relative.replace(os.sep, "/")
    except (TypeError, ValueError, OSError):
        return None


def _append(root: str, item: Mapping[str, Any]) -> None:
    path = os.path.join(root, TRACE)
    line = json.dumps(dict(item), sort_keys=True, ensure_ascii=False) + "\n"
    # A single append-mode write keeps each small hook event on one record.
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(line)
        stream.flush()


def event(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Translate and record one Claude Code hook payload.

    Unsupported events, payloads with no active session, and paths outside
    that session are harmless no-ops. A failed/missing Read is translated for
    the caller but is not evidence of an input and therefore is not traced.
    """
    if not isinstance(payload, Mapping):
        return None
    root = _workspace(payload)
    if root is None:
        return None

    hook = payload.get("hook_event_name")
    record = True
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        item = {"event": "prompt", "prompt": prompt, "ts": time.time()}
    elif hook == "PostToolUse":
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, Mapping):
            return None
        tool = payload.get("tool_name")
        if tool in ("Write", "Edit", "MultiEdit"):
            path = _relative_file(root, tool_input.get("file_path"))
            if path is None:
                return None
            item = {"event": "write", "path": path, "ts": time.time()}
        elif tool == "Read":
            path = _relative_file(root, tool_input.get("file_path"))
            if path is None:
                return None
            item = {"event": "read", "path": path, "ts": time.time()}
            record = os.path.isfile(os.path.join(root, path))
        elif tool == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str):
                return None
            item = {"event": "bash", "cmd": command, "ts": time.time()}
        else:
            return None
    else:
        return None

    if record:
        _append(root, item)
    return item


def _hook(command: str, matcher: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        value["matcher"] = matcher
    return value


def _contains(entries: Any) -> bool:
    if not isinstance(entries, list):
        return False
    for group in entries:
        if not isinstance(group, Mapping) or not isinstance(group.get("hooks"), list):
            continue
        for hook in group["hooks"]:
            if (isinstance(hook, Mapping) and hook.get("type") == "command"
                    and hook.get("command") == _COMMAND):
                return True
    return False


def _write_json(path: str, value: Mapping[str, Any]) -> None:
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(project: str | os.PathLike[str]) -> dict[str, Any]:
    """Install both Claude hook bindings while preserving other settings.

    If both bindings are already present the settings file is not rewritten.
    """
    root = os.path.abspath(os.fspath(project))
    directory = os.path.join(root, ".claude")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "settings.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as stream:
            settings = json.load(stream)
        if not isinstance(settings, dict):
            raise ValueError("Claude settings must be a JSON object")
    else:
        settings = {}

    hooks = settings.get("hooks")
    if hooks is None:
        hooks = {}
        settings["hooks"] = hooks
    elif not isinstance(hooks, dict):
        raise ValueError("Claude hooks setting must be a JSON object")

    if all(_contains(hooks.get(name)) for name in _EVENTS):
        return {"status": "already wired", "wired": list(_EVENTS), "path": path}

    if not _contains(hooks.get("UserPromptSubmit")):
        entries = hooks.setdefault("UserPromptSubmit", [])
        if not isinstance(entries, list):
            raise ValueError("Claude UserPromptSubmit hooks must be a list")
        entries.append(_hook(_COMMAND))
    if not _contains(hooks.get("PostToolUse")):
        entries = hooks.setdefault("PostToolUse", [])
        if not isinstance(entries, list):
            raise ValueError("Claude PostToolUse hooks must be a list")
        entries.append(_hook(_COMMAND, "Write|Edit|MultiEdit|Read|Bash"))

    _write_json(path, settings)
    return {"status": "wired", "wired": list(_EVENTS), "path": path}


def main() -> int:
    """Receive one hook payload on stdin without ever blocking the agent."""
    try:
        event(json.load(sys.stdin))
    except (OSError, ValueError, TypeError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TRACE", "event", "install", "main"]
