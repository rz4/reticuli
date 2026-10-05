"""Claude Code hook adapter for a Reticuli authoring session.

Hook payloads are read from stdin by ``main``.  A workspace is a session
only while its ``.reticuli`` directory exists; accepted events are appended
to the authoring trace there.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import time


TRACE = os.path.join(".reticuli", "draft.jsonl")
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _session(payload: dict) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    directory = os.path.realpath(cwd)
    return directory if os.path.isdir(os.path.join(directory, ".reticuli")) else None


def _relative_file(directory: str, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = os.path.realpath(os.path.join(directory, value))
    if os.path.commonpath((directory, path)) != directory or path == directory:
        return None
    return os.path.relpath(path, directory).replace(os.sep, "/")


def event(payload: dict) -> dict | None:
    """Translate one hook payload and append it to the active session trace."""
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
        args = payload.get("tool_input")
        if not isinstance(args, dict):
            args = {}
        if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            path = _relative_file(directory, args.get("file_path") or args.get("notebook_path"))
            if path is not None:
                row = {"event": "write", "path": path}
        elif tool == "Read":
            path = _relative_file(directory, args.get("file_path"))
            if path is not None:
                row = {"event": "read", "path": path}
        elif tool == "Bash" and isinstance(args.get("command"), str):
            row = {"event": "bash", "cmd": args["command"]}

    if row is None:
        return None
    row["ts"] = time.time()
    # A PostToolUse read can be reported for an absent path by a synthetic
    # payload.  Only actual reads can become pinned authoring inputs.
    if row["event"] != "read" or os.path.isfile(os.path.join(directory, row["path"])):
        with open(os.path.join(directory, TRACE), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def install(project: str) -> dict:
    """Wire both supported Claude hooks into project settings once."""
    settings = os.path.join(os.path.abspath(project), ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings), exist_ok=True)
    if os.path.isfile(settings):
        with open(settings, encoding="utf-8") as stream:
            data = json.load(stream)
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    command = shlex.quote(sys.executable) + " -m reticuli.hooks"
    wired = []
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError("Claude hook entries must be a list")
        exists = any(isinstance(group, dict) and any(
            isinstance(item, dict) and item.get("command") == command
            for item in group.get("hooks", []) if isinstance(group.get("hooks"), list)
        ) for group in entries)
        if not exists:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            wired.append(name)
    if wired:
        with open(settings, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if wired else "already wired", "wired": wired or list(HOOK_EVENTS),
            "settings": settings}


def main() -> None:
    try:
        event(json.load(sys.stdin))
    except (ValueError, OSError):
        return


if __name__ == "__main__":
    main()
