"""Claude Code hook adapter for a Reticuli authoring session."""

import json
import os
import time


TRACE = os.path.join(".reticuli", "draft.jsonl")


def _session(payload):
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(os.path.join(cwd, ".reticuli")):
        return None
    return os.path.realpath(cwd)


def _relative_file(cwd, path):
    if not isinstance(path, str) or not path:
        return None
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
    try:
        if os.path.commonpath((cwd, full)) != cwd or full == cwd:
            return None
    except ValueError:
        return None
    return os.path.relpath(full, cwd).replace(os.sep, "/")


def event(payload):
    """Record a recognized hook event and return its trace row, or None."""
    if not isinstance(payload, dict):
        return None
    cwd = _session(payload)
    if cwd is None:
        return None
    hook = payload.get("hook_event_name")
    row = None
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "text": prompt}
    elif hook == "PostToolUse":
        tool = payload.get("tool_name")
        arguments = payload.get("tool_input")
        if not isinstance(arguments, dict):
            arguments = {}
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            path = _relative_file(cwd, arguments.get("file_path"))
            if path is not None:
                row = {"event": "read" if tool == "Read" else "write", "path": path}
        elif tool == "Bash":
            command = arguments.get("command")
            if isinstance(command, str) and command:
                row = {"event": "bash", "cmd": command}
    if row is None:
        return None
    row["ts"] = time.time()
    with open(os.path.join(cwd, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Install both hook commands without changing unrelated Claude settings."""
    settings = os.path.join(os.fspath(project), ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings), exist_ok=True)
    try:
        with open(settings, encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    wired = []
    for name in ("UserPromptSubmit", "PostToolUse"):
        command = "python3 -m reticuli.hooks"
        entry = {"hooks": [{"type": "command", "command": command}]}
        current = hooks.setdefault(name, [])
        if entry not in current:
            current.append(entry)
            wired.append(name)
    if wired:
        with open(settings, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if wired else "already wired", "wired": wired or list(("UserPromptSubmit", "PostToolUse"))}


if __name__ == "__main__":
    import sys
    try:
        event(json.load(sys.stdin))
    except (OSError, ValueError):
        pass
