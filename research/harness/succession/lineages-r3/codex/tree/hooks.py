"""Claude Code hook adapter for a Reticuli authoring session.

Only a workspace with a ``.reticuli`` directory records events.  The draft
trace is residue; it is not part of a claim's identity.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path


TRACE = os.path.join(".reticuli", "draft.jsonl")
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _session(payload: dict) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    workspace = os.path.realpath(cwd)
    if not os.path.isdir(os.path.join(workspace, ".reticuli")):
        return None
    return workspace


def _relative_file(workspace: str, name: object) -> str | None:
    if not isinstance(name, str) or not name:
        return None
    absolute = os.path.realpath(name if os.path.isabs(name) else os.path.join(workspace, name))
    if os.path.commonpath((workspace, absolute)) != workspace or absolute == workspace:
        return None
    return os.path.relpath(absolute, workspace).replace(os.sep, "/")


def event(payload: dict) -> dict | None:
    """Translate one hook payload and append its trace event, if applicable."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    hook = payload.get("hook_event_name")
    row: dict | None = None
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            row = {"event": "prompt", "text": prompt}
    elif hook == "PostToolUse":
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
    # A read can name a file that was not present (for example a failed or
    # speculative tool call).  It is still a read event to the caller, but
    # there are no bytes for the authoring layer to pin as an input.
    if row["event"] == "read" and not os.path.isfile(os.path.join(workspace, row["path"])):
        return row
    row["ts"] = time.time()
    with open(os.path.join(workspace, TRACE), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def _command() -> str:
    package_root = str(Path(__file__).resolve().parent.parent)
    code = f"import sys; sys.path.insert(0, {package_root!r}); from reticuli.hooks import main; main()"
    return " ".join(shlex.quote(part) for part in (sys.executable, "-c", code))


def install(project: str) -> dict:
    """Add the two project hooks without replacing unrelated Claude settings."""
    settings_path = os.path.join(project, ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as stream:
            settings = json.load(stream)
    else:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError("Claude settings must be a JSON object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks settings must be a JSON object")
    command = _command()
    changed = False
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be an array")
        if not any(isinstance(entry, dict) and any(
            isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command") == command
            for hook in entry.get("hooks", []) if isinstance(entry.get("hooks"), list)
        ) for entry in entries):
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
    if changed:
        with open(settings_path, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": list(HOOK_EVENTS)}


def main() -> None:
    event(json.load(sys.stdin))


if __name__ == "__main__":
    main()
