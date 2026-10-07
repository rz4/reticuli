"""Translate coding-agent hooks into an authoring session trace."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


TRACE = ".reticuli/draft.jsonl"
_COMMAND = "python3 -m reticuli.hooks"
_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _session(payload: dict) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    directory = os.path.realpath(cwd)
    if not os.path.isdir(os.path.join(directory, ".reticuli")):
        return None
    return directory


def _path(directory: str, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    absolute = os.path.realpath(os.path.join(directory, value))
    if os.path.commonpath((directory, absolute)) != directory or absolute == directory:
        return None
    relative = os.path.relpath(absolute, directory).replace(os.sep, "/")
    if relative.startswith(".reticuli/") or relative == ".reticuli":
        return None
    return relative


def event(payload: dict) -> dict | None:
    """Append one recognized hook event; ignore payloads outside a session."""
    if not isinstance(payload, dict):
        return None
    directory = _session(payload)
    if directory is None:
        return None

    kind = payload.get("hook_event_name")
    entry: dict
    if kind == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        entry = {"event": "prompt", "prompt": prompt}
    elif kind == "PostToolUse":
        tool = payload.get("tool_name")
        arguments = payload.get("tool_input")
        if not isinstance(arguments, dict):
            return None
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            path = _path(directory, arguments.get("file_path"))
            if path is None:
                return None
            entry = {"event": "read" if tool == "Read" else "write", "path": path}
        elif tool == "Bash":
            command = arguments.get("command")
            if not isinstance(command, str) or not command:
                return None
            entry = {"event": "bash", "cmd": command}
        else:
            return None
    else:
        return None

    entry["ts"] = time.time()
    with open(os.path.join(directory, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def install(project: str | os.PathLike[str]) -> dict:
    """Add the hook command to project settings without changing other keys."""
    settings = Path(project) / ".claude" / "settings.json"
    try:
        document = json.loads(settings.read_text(encoding="utf-8"))
    except FileNotFoundError:
        document = {}
    if not isinstance(document, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")

    changed = False
    for name in _EVENTS:
        groups = hooks.setdefault(name, [])
        if not isinstance(groups, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        already = any(
            isinstance(group, dict)
            and isinstance(group.get("hooks"), list)
            and any(isinstance(item, dict) and item.get("command") == _COMMAND
                    for item in group["hooks"])
            for group in groups
        )
        if not already:
            groups.append({"hooks": [{"type": "command", "command": _COMMAND}]})
            changed = True

    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return {"status": "wired" if changed else "already wired", "wired": list(_EVENTS)}


def main() -> int:
    try:
        event(json.load(sys.stdin))
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
