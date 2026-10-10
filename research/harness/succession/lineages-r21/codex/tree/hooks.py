"""Translate Claude Code hooks into a Reticuli session trace."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time

from ._util import locked_append

TRACE = ".reticuli/draft.jsonl"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _relative_file(cwd, value):
    """Return a session-relative file name, or None for an outside path."""
    if not isinstance(value, str) or not value:
        return None
    base = os.path.realpath(cwd)
    path = os.path.realpath(value if os.path.isabs(value) else os.path.join(base, value))
    try:
        if os.path.commonpath((base, path)) != base or path == base:
            return None
    except ValueError:
        return None
    return os.path.relpath(path, base).replace(os.sep, "/")


def event(payload):
    """Record one supported hook payload and return its normalized event."""
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(os.path.join(cwd, ".reticuli")):
        return None
    kind = payload.get("hook_event_name")
    row = None
    if kind == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "prompt": prompt}
    elif kind == "PostToolUse":
        tool = payload.get("tool_name")
        info = payload.get("tool_input")
        if isinstance(info, dict):
            if tool in ("Write", "Edit", "MultiEdit", "Read"):
                name = _relative_file(cwd, info.get("file_path"))
                if name is not None:
                    row = {"event": "read" if tool == "Read" else "write", "path": name}
            elif tool == "Bash" and isinstance(info.get("command"), str):
                row = {"event": "bash", "cmd": info["command"]}
    if row is None:
        return None
    row["ts"] = time.time()
    # A reported read of a missing file is useful to the caller, but it
    # cannot become a pinned input when the session is sealed.
    if row["event"] != "read" or os.path.isfile(os.path.join(cwd, row["path"])):
        locked_append(os.path.join(cwd, TRACE), json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Add the two hook commands without changing unrelated settings."""
    settings_path = os.path.join(project, ".claude", "settings.json")
    try:
        with open(settings_path, encoding="utf-8") as stream:
            settings = json.load(stream)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    command = f"{shlex.quote(sys.executable)} -m reticuli.hooks"
    wired = []
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude hook {name} must be a list")
        if any(command == hook.get("command") for entry in entries if isinstance(entry, dict)
               for hook in entry.get("hooks", []) if isinstance(hook, dict)):
            continue
        entries.append({"hooks": [{"type": "command", "command": command}]})
        wired.append(name)
    if not wired:
        return {"status": "already wired", "wired": list(HOOK_EVENTS)}
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as stream:
        json.dump(settings, stream, indent=2)
        stream.write("\n")
    return {"status": "wired", "wired": wired}


def main():
    try:
        event(json.load(sys.stdin))
    except (ValueError, OSError):
        pass


if __name__ == "__main__":
    main()
