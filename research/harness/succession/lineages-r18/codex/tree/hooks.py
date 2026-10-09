"""Claude Code hooks that record a workspace session for claim authoring."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time

TRACE = os.path.join(".reticuli", "draft.jsonl")
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_READ_TOOLS = frozenset({"Read"})
_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _workspace(payload: dict) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    workspace = os.path.realpath(cwd)
    store = os.path.join(workspace, ".reticuli")
    if not os.path.isdir(workspace) or not os.path.isdir(store) or os.path.islink(store):
        return None
    return workspace


def _relative_file(workspace: str, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value if os.path.isabs(value) else os.path.join(workspace, value)
    resolved = os.path.realpath(candidate)
    try:
        if os.path.commonpath((workspace, resolved)) != workspace or resolved == workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(resolved, workspace)
    if relative == ".reticuli" or relative.startswith(".reticuli" + os.sep):
        return None
    return relative.replace(os.sep, "/")


def event(payload: dict) -> dict | None:
    """Translate and append one recognized hook payload, or ignore it."""
    if not isinstance(payload, dict):
        return None
    workspace = _workspace(payload)
    if workspace is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        entry = {"event": "prompt", "text": prompt}
    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        if tool in _WRITE_TOOLS or tool in _READ_TOOLS:
            path = _relative_file(workspace, tool_input.get("file_path"))
            if path is None:
                return None
            entry = {"event": "write" if tool in _WRITE_TOOLS else "read", "path": path}
        elif tool == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str) or not command:
                return None
            entry = {"event": "bash", "cmd": command}
        else:
            return None
    else:
        return None

    entry["ts"] = time.time()
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _command() -> str:
    source_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return ("PYTHONPATH=" + shlex.quote(source_root) + ":$PYTHONPATH "
            + shlex.quote(sys.executable) + " -m reticuli.hooks")


def install(project: os.PathLike[str] | str) -> dict:
    """Add the hook command to project settings without replacing other settings."""
    settings_path = os.path.join(os.fspath(project), ".claude", "settings.json")
    try:
        with open(settings_path, encoding="utf-8") as stream:
            settings = json.load(stream)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks settings must be a JSON object")

    command = _command()
    wired = []
    changed = False
    for name in _EVENTS:
        groups = hooks.setdefault(name, [])
        if not isinstance(groups, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        present = any(isinstance(group, dict) and
                      any(isinstance(item, dict) and item.get("command") == command
                          for item in group.get("hooks", []))
                      for group in groups)
        if not present:
            groups.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
        wired.append(name)

    if changed:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": wired}


def main() -> int:
    """Receive one JSON payload from a Claude command hook."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    event(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
