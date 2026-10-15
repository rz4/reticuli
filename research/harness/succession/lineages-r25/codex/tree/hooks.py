"""Translate Claude Code hooks into a Reticuli authoring trace."""

import json
import os
import sys
import time

from .authoring import TRACE


def _session(payload):
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    directory = os.path.realpath(cwd)
    return directory if os.path.isdir(os.path.join(directory, ".reticuli")) else None


def _relative(directory, path):
    if not isinstance(path, str) or not path:
        return None
    absolute = os.path.realpath(path if os.path.isabs(path) else os.path.join(directory, path))
    try:
        if os.path.commonpath((directory, absolute)) != directory:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(absolute, directory)
    return relative.replace(os.sep, "/") if relative != "." else None


def event(payload):
    """Record a supported hook event, returning its trace row or ``None``."""
    if not isinstance(payload, dict):
        return None
    directory = _session(payload)
    if directory is None:
        return None

    hook = payload.get("hook_event_name")
    row = None
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "prompt": prompt}
    elif hook == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            path = _relative(directory, tool_input.get("file_path"))
            if path is not None:
                row = {"event": "read" if tool == "Read" else "write", "path": path}
        elif tool == "Bash":
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                row = {"event": "bash", "cmd": command}
    if row is None:
        return None

    row["ts"] = time.time()
    # A failed or speculative Read has no bytes to pin as an input.
    if row["event"] != "read" or os.path.isfile(os.path.join(directory, row["path"])):
        with open(os.path.join(directory, TRACE), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Add Reticuli's two hooks to Claude settings without changing other keys."""
    settings = os.path.join(os.path.abspath(project), ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings), exist_ok=True)
    try:
        with open(settings, encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError:
        document = {}
    if not isinstance(document, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks settings must be a JSON object")

    command = "python3 -m reticuli.hooks"
    wired = []
    changed = False
    for name in ("UserPromptSubmit", "PostToolUse"):
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        present = any(
            isinstance(entry, dict)
            and any(isinstance(hook, dict) and hook.get("command") == command
                    for hook in entry.get("hooks", []) if isinstance(entry.get("hooks"), list))
            for entry in entries
        )
        if not present:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
        wired.append(name)
    if changed:
        with open(settings, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": wired}


def main():
    try:
        event(json.load(sys.stdin))
    except (ValueError, OSError):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
