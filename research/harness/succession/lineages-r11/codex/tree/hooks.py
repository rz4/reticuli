"""Translate Claude Code hooks into a local claim-authoring trace."""

import json
import os
import sys
import time


TRACE = ".reticuli/draft.jsonl"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
COMMAND = "python3 -m reticuli.hooks"


def _relative_file(workspace, name):
    """Return a confined relative path, including for a file not yet created."""
    if not isinstance(name, str) or not name:
        return None
    path = name if os.path.isabs(name) else os.path.join(workspace, name)
    path = os.path.realpath(path)
    try:
        if os.path.commonpath((workspace, path)) != workspace or path == workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(path, workspace)
    if relative == ".reticuli" or relative.startswith(".reticuli" + os.sep):
        return None
    return relative.replace(os.sep, "/")


def event(payload):
    """Append one recognized hook event and return it; otherwise do nothing."""
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    workspace = os.path.realpath(cwd)
    if not os.path.isdir(os.path.join(workspace, ".reticuli")):
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
        if not isinstance(tool_input, dict):
            return None
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            path = _relative_file(workspace, tool_input.get("file_path"))
            if path is not None:
                row = {"event": "read" if tool == "Read" else "write", "path": path}
        elif tool == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                row = {"event": "bash", "cmd": command}
    if row is None:
        return None
    row["ts"] = time.time()
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Wire the two supported events into Claude Code project settings."""
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
    wired = []
    changed = False
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        present = any(
            isinstance(entry, dict) and any(
                isinstance(hook, dict) and hook.get("type") == "command"
                and hook.get("command") == COMMAND
                for hook in entry.get("hooks", []) if isinstance(entry.get("hooks"), list)
            ) for entry in entries
        )
        if not present:
            entries.append({"hooks": [{"type": "command", "command": COMMAND}]})
            changed = True
        wired.append(name)
    if changed:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as stream:
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
