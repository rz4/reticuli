"""Claude Code hook adapter for a Reticuli authoring session."""
from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
import time
from typing import Any


TRACE = os.path.join(".reticuli", "draft.jsonl")
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
FILE_TOOLS = {
    "Write": "write",
    "Edit": "write",
    "MultiEdit": "write",
    "NotebookEdit": "write",
    "Read": "read",
}


def _session(cwd: Any) -> str | None:
    if not isinstance(cwd, str) or not cwd:
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, ".reticuli")) else None


def _relative_file(workspace: str, file_path: Any) -> str | None:
    if not isinstance(file_path, str) or not file_path:
        return None
    candidate = os.path.realpath(os.path.join(workspace, file_path))
    try:
        if os.path.commonpath((workspace, candidate)) != workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(candidate, workspace)
    if relative == "." or relative == ".." or relative.startswith(".." + os.sep):
        return None
    return relative.replace(os.sep, "/")


def event(payload: Any) -> dict[str, Any] | None:
    """Append one supported hook event, or do nothing outside a session."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload.get("cwd"))
    if workspace is None:
        return None

    name = payload.get("hook_event_name")
    row: dict[str, Any]
    if name == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        row = {"event": "prompt", "prompt": prompt}
    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        if tool in FILE_TOOLS:
            path = _relative_file(workspace, tool_input.get("file_path"))
            if path is None:
                return None
            row = {"event": FILE_TOOLS[tool], "path": path}
        elif tool == "Bash":
            command = tool_input.get("command")
            if not isinstance(command, str) or not command:
                return None
            row = {"event": "bash", "cmd": command}
        else:
            return None
    else:
        return None

    row["ts"] = time.time()
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project: os.PathLike[str] | str) -> dict[str, Any]:
    """Add Reticuli's two hooks to Claude project settings once."""
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
        raise ValueError("Claude hooks setting must be a JSON object")

    command = shlex.quote(sys.executable) + " " + shlex.quote(os.path.abspath(__file__))
    changed = False
    for hook_name in HOOK_EVENTS:
        groups = hooks.setdefault(hook_name, [])
        if not isinstance(groups, list):
            raise ValueError(f"Claude {hook_name} hooks must be a list")
        wired = any(
            isinstance(group, dict) and isinstance(group.get("hooks"), list)
            and any(isinstance(item, dict) and item.get("type") == "command"
                    and item.get("command") == command for item in group["hooks"])
            for group in groups
        )
        if not wired:
            groups.append({"hooks": [{"type": "command", "command": command}]})
            changed = True

    if changed:
        parent = os.path.dirname(settings_path)
        os.makedirs(parent, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                             prefix=".settings-", delete=False) as stream:
                temporary = stream.name
                json.dump(settings, stream, indent=2)
                stream.write("\n")
            os.replace(temporary, settings_path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
    return {"status": "wired" if changed else "already wired", "wired": list(HOOK_EVENTS)}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        event(payload)
    except (OSError, ValueError, TypeError) as exc:
        print(f"reticuli hook: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
