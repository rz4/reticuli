"""Translate coding-agent hooks into a claim session trace."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .authoring import TRACE


def _session(payload):
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    workspace = os.path.realpath(cwd)
    if not os.path.isdir(os.path.join(workspace, ".reticuli")):
        return None
    return workspace


def _path(workspace, value):
    if not isinstance(value, str) or not value:
        return None
    target = os.path.realpath(os.path.join(workspace, value))
    if target == workspace or os.path.commonpath((workspace, target)) != workspace:
        return None
    return os.path.relpath(target, workspace)


def event(payload):
    """Record one meaningful hook event, or return None outside a session."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    kind = payload.get("hook_event_name")
    row = None
    if kind == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "prompt": prompt}
    elif kind == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Read"):
                path = _path(workspace, tool_input.get("file_path"))
                if path is not None:
                    row = {"event": "read" if tool == "Read" else "write", "path": path}
            elif tool == "Bash":
                command = tool_input.get("command")
                if isinstance(command, str) and command:
                    row = {"event": "bash", "cmd": command}
    if row is None:
        return None

    row["ts"] = time.time()
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as trace:
        trace.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Wire the two supported Claude Code hooks into project settings."""
    settings = Path(project) / ".claude" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read Claude settings: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    command = f"{sys.executable} -m reticuli.hooks"
    wired = []
    changed = False
    for name in ("UserPromptSubmit", "PostToolUse"):
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude hook {name} must be a list")
        if not any(isinstance(entry, dict) and any(
            isinstance(hook, dict) and hook.get("command") == command
            for hook in entry.get("hooks", []) if isinstance(entry.get("hooks"), list)
        ) for entry in entries):
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
        wired.append(name)
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"status": "wired" if changed else "already wired", "wired": wired}


def main():
    try:
        event(json.load(sys.stdin))
    except (ValueError, OSError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
