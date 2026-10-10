"""Claude Code hooks that record a claim-authoring session."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time


TRACE = ".reticuli/draft.jsonl"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _session(payload):
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, ".reticuli")) else None


def _path(workspace, value):
    if not isinstance(value, str) or not value:
        return None
    target = os.path.realpath(value if os.path.isabs(value) else os.path.join(workspace, value))
    try:
        if os.path.commonpath((workspace, target)) != workspace or target == workspace:
            return None
    except ValueError:
        return None
    return os.path.relpath(target, workspace).replace(os.sep, "/")


def event(payload):
    """Translate one hook payload to a trace event, or ignore it."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    hook = payload.get("hook_event_name")
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        row = {"event": "prompt", "prompt": prompt}
    elif hook == "PostToolUse":
        tool = payload.get("tool_name")
        args = payload.get("tool_input")
        if not isinstance(args, dict):
            return None
        if tool == "Bash":
            command = args.get("command")
            if not isinstance(command, str):
                return None
            row = {"event": "bash", "cmd": command}
        elif tool in ("Read", "Write", "Edit", "MultiEdit"):
            path = _path(workspace, args.get("file_path"))
            if path is None:
                return None
            row = {"event": "read" if tool == "Read" else "write", "path": path}
        else:
            return None
    else:
        return None

    row["ts"] = time.time()
    # A tool may report a failed read. It is still a read event for the hook
    # caller, but an absent file cannot become a pinned input of a claim.
    if row["event"] != "read" or os.path.isfile(os.path.join(workspace, row["path"])):
        with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Add this hook to project settings while preserving unrelated settings."""
    project = os.path.realpath(os.fspath(project))
    settings_path = os.path.join(project, ".claude", "settings.json")
    if os.path.isfile(settings_path):
        with open(settings_path, encoding="utf-8") as stream:
            settings = json.load(stream)
        if not isinstance(settings, dict):
            raise ValueError("Claude settings must be a JSON object")
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks settings must be a JSON object")
    command = shlex.quote(sys.executable) + " -m reticuli.hooks"
    wired = []
    changed = False
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be an array")
        present = any(isinstance(entry, dict) and any(
            isinstance(item, dict) and item.get("command") == command
            for item in entry.get("hooks", []) if isinstance(entry.get("hooks"), list)
        ) for entry in entries)
        if not present:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
        wired.append(name)

    if changed:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": wired}


def main():
    payload = json.load(sys.stdin)
    event(payload)


if __name__ == "__main__":
    main()
