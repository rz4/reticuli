"""Claude Code hook bridge for draft claim sessions."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time

from ._util import locked_append

TRACE = ".reticuli/draft.jsonl"


def _session(payload):
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, ".reticuli")) else None


def _relative(workspace, name):
    if not isinstance(name, str) or not name:
        return None
    path = os.path.realpath(os.path.join(workspace, name))
    try:
        if os.path.commonpath((workspace, path)) != workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(path, workspace)
    return None if relative == "." else relative.replace(os.sep, "/")


def event(payload):
    """Map one hook payload to a draft event and record observed activity."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None
    hook = payload.get("hook_event_name")
    row = None
    record = True
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "prompt": prompt}
    elif hook == "PostToolUse":
        tool = payload.get("tool_name")
        source = payload.get("tool_input")
        source = source if isinstance(source, dict) else {}
        if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Read"):
            name = _relative(workspace, source.get("file_path") or source.get("notebook_path"))
            if name is None:
                return None
            row = {"event": "read" if tool == "Read" else "write", "path": name}
            if tool == "Read" and not os.path.isfile(os.path.join(workspace, name)):
                record = False
        elif tool == "Bash" and isinstance(source.get("command"), str):
            row = {"event": "bash", "cmd": source["command"]}
    if row is None:
        return None
    row["ts"] = time.time()
    if record:
        locked_append(os.path.join(workspace, TRACE), json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project):
    """Add this bridge to project hooks while preserving other settings."""
    path = os.path.join(os.fspath(project), ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as stream:
            settings = json.load(stream)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("Claude settings must be a JSON object")
    wiring = settings.setdefault("hooks", {})
    if not isinstance(wiring, dict):
        raise ValueError("Claude hooks must be a JSON object")
    command = shlex.quote(sys.executable) + " -m reticuli.hooks"
    names = ("UserPromptSubmit", "PostToolUse")
    added = []
    for name in names:
        entries = wiring.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude hook {name} must be a list")
        present = any(
            isinstance(group, dict)
            and isinstance(group.get("hooks"), list)
            and any(isinstance(hook, dict) and hook.get("command") == command
                    for hook in group["hooks"])
            for group in entries
        )
        if not present:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            added.append(name)
    if added:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if added else "already wired", "wired": list(names)}


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    event(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
