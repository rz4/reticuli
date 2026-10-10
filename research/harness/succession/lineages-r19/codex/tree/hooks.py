"""Translate coding-agent hooks into a local authoring session trace."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


TRACE = ".reticuli/draft.jsonl"
_HOOKS = ("UserPromptSubmit", "PostToolUse")
_COMMAND = "python3 -m reticuli.hooks"


def _session(payload):
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, ".reticuli")) else None


def _path(workspace, value):
    if not isinstance(value, str) or not value:
        return None
    candidate = value if os.path.isabs(value) else os.path.join(workspace, value)
    resolved = os.path.realpath(candidate)
    try:
        if os.path.commonpath((workspace, resolved)) != workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(resolved, workspace)
    return relative.replace(os.sep, "/") if relative != "." else None


def event(payload):
    """Return a trace event for a supported payload and append it to the session.

    A hook outside a session, or a file outside its workspace, has no effect.
    Reads of files that do not exist are useful to callers but cannot become
    authoring inputs, so only existing reads are recorded.
    """
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        row = {"event": "prompt", "prompt": prompt}
    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        args = payload.get("tool_input")
        if not isinstance(args, dict):
            return None
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            path = _path(workspace, args.get("file_path"))
            if path is None:
                return None
            row = {"event": "read" if tool == "Read" else "write", "path": path}
        elif tool == "Bash":
            command = args.get("command")
            if not isinstance(command, str):
                return None
            row = {"event": "bash", "cmd": command}
        else:
            return None
    else:
        return None

    stamped = {**row, "ts": time.time()}
    if row["event"] != "read" or os.path.isfile(os.path.join(workspace, row["path"])):
        with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(stamped, sort_keys=True) + "\n")
    return stamped


def install(project):
    """Wire the two supported Claude hooks, preserving other settings."""
    settings_path = Path(project) / ".claude" / "settings.json"
    if settings_path.exists():
        with settings_path.open(encoding="utf-8") as stream:
            settings = json.load(stream)
        if not isinstance(settings, dict):
            raise ValueError("Claude settings must be a JSON object")
    else:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    wired = []
    changed = False
    for name in _HOOKS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        present = any(isinstance(entry, dict) and any(
            isinstance(item, dict) and item.get("type") == "command"
            and item.get("command") == _COMMAND
            for item in entry.get("hooks", []) if isinstance(entry.get("hooks"), list))
            for entry in entries)
        if not present:
            entries.append({"hooks": [{"type": "command", "command": _COMMAND}]})
            changed = True
        wired.append(name)
    if changed or not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with settings_path.open("w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": wired}


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    event(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
