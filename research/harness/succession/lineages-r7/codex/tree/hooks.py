"""Claude Code hooks that record a workspace session for claim authoring."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

from ._util import safe_path


TRACE = ".reticuli/draft.jsonl"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _session(payload):
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, ".reticuli")) else None


def _relative_file(workspace, path):
    if not isinstance(path, str) or not path:
        return None
    candidate = path if os.path.isabs(path) else os.path.join(workspace, path)
    candidate = os.path.realpath(candidate)
    try:
        if os.path.commonpath((workspace, candidate)) != workspace:
            return None
        name = os.path.relpath(candidate, workspace).replace(os.sep, "/")
        safe_path(workspace, name)
    except (ValueError, OSError):
        return None
    except Exception as error:
        # A tool may report a file that cannot be represented as a claim path.
        from . import kernel
        if isinstance(error, kernel.ClaimError):
            return None
        raise
    return name


def event(payload):
    """Convert a Claude hook payload to one trace event, or ignore it."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    hook = payload.get("hook_event_name")
    row = None
    if hook == "UserPromptSubmit" and isinstance(payload.get("prompt"), str):
        row = {"event": "prompt", "prompt": payload["prompt"]}
    elif hook == "PostToolUse":
        tool = payload.get("tool_name")
        given = payload.get("tool_input")
        given = given if isinstance(given, dict) else {}
        if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Read"):
            name = _relative_file(workspace, given.get("file_path") or given.get("notebook_path"))
            if name is not None:
                row = {"event": "read" if tool == "Read" else "write", "path": name}
        elif tool == "Bash" and isinstance(given.get("command"), str):
            row = {"event": "bash", "cmd": given["command"]}
    if row is None:
        return None
    row["ts"] = time.time()
    if row["event"] == "read" and not os.path.isfile(os.path.join(workspace, row["path"])):
        return row
    trace = os.path.join(workspace, TRACE)
    with open(trace, "a", encoding="utf-8") as target:
        target.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def _command():
    package_root = str(Path(__file__).resolve().parent.parent)
    return ("PYTHONPATH=" + shlex.quote(package_root) + " "
            + shlex.quote(sys.executable) + " -m reticuli.hooks")


def install(project):
    """Install the two hook commands, retaining unrelated Claude settings."""
    settings = Path(project) / ".claude" / "settings.json"
    if settings.exists():
        with settings.open(encoding="utf-8") as source:
            document = json.load(source)
        if not isinstance(document, dict):
            raise ValueError("Claude settings must be a JSON object")
    else:
        document = {}
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude hooks must be a JSON object")
    command = _command()
    changed = False
    for name in HOOK_EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"Claude {name} hooks must be a list")
        installed = any(
            isinstance(group, dict) and any(
                isinstance(item, dict) and item.get("command") == command
                for item in group.get("hooks", [])
            ) for group in entries
        )
        if not installed:
            entries.append({"hooks": [{"type": "command", "command": command}]})
            changed = True
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        with settings.open("w", encoding="utf-8") as target:
            json.dump(document, target, indent=2)
            target.write("\n")
    return {"status": "wired" if changed else "already wired",
            "wired": list(HOOK_EVENTS)}


def main():
    payload = json.load(sys.stdin)
    event(payload)


if __name__ == "__main__":
    main()
