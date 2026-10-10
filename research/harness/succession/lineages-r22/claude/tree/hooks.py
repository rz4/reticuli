"""Agents: the coding-agent handshake (spec/layers.md).

`event` turns one Claude Code hook payload into a trace event appended to
the session's trace (`authoring.TRACE`) -- guarded both ways: a `cwd` that
is not a reticuli session (no `.reticuli/` under it) is a no-op, and a
tool-use path that resolves outside the session is ignored rather than
traced. A hook event name this module does not recognize maps to nothing.
`install` wires the handshake into a project's `.claude/settings.json`,
idempotently, touching nothing else already there.
"""
import json
import os
import sys
import time

from . import authoring
from . import kernel

HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
HOOK_COMMAND = "python3 -m reticuli.hooks"

_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _has_session(cwd) -> bool:
    return bool(cwd) and os.path.isdir(os.path.join(cwd, kernel.STORE))


def _relpath_within(ws: str, file_path) -> str:
    """The path of `file_path` relative to `ws`, or `None` if it is not a
    real descendant of `ws` -- lexical containment only, no requirement
    that the file already exist."""
    if not file_path:
        return None
    ws_real = os.path.realpath(ws)
    target_real = os.path.realpath(file_path)
    rel = os.path.relpath(target_real, ws_real)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


def _append_trace(ws: str, record: dict) -> None:
    path = os.path.join(ws, authoring.TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def event(payload: dict):
    """Map one hook payload to a trace event, append it to the session's
    trace, and return it -- or return `None` for a non-event, a missing
    session, or a path outside the session."""
    cwd = payload.get("cwd")
    if not _has_session(cwd):
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        rec = {"event": "prompt", "prompt": payload.get("prompt", ""), "ts": time.time()}
    elif name == "PostToolUse":
        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input") or {}
        if tool_name == "Bash":
            cmd = tool_input.get("command")
            if not cmd:
                return None
            rec = {"event": "bash", "cmd": cmd, "ts": time.time()}
        elif tool_name in _WRITE_TOOLS:
            rel = _relpath_within(cwd, tool_input.get("file_path"))
            if rel is None:
                return None
            rec = {"event": "write", "path": rel, "ts": time.time()}
        elif tool_name == "Read":
            rel = _relpath_within(cwd, tool_input.get("file_path"))
            if rel is None:
                return None
            rec = {"event": "read", "path": rel, "ts": time.time()}
        else:
            return None
    else:
        return None

    _append_trace(cwd, rec)
    return rec


def _is_wired(entries) -> bool:
    for group in entries or []:
        for h in group.get("hooks", []):
            if h.get("type") == "command" and h.get("command") == HOOK_COMMAND:
                return True
    return False


def install(proj: str) -> dict:
    """Wire the agent handshake into `proj`'s `.claude/settings.json`:
    one hook entry per event in `HOOK_EVENTS`, added only if not already
    present. Idempotent -- a second call touches nothing on disk -- and
    every other key already in the file survives untouched."""
    settings_path = os.path.join(proj, ".claude", "settings.json")
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_block = settings.setdefault("hooks", {})
    if all(_is_wired(hooks_block.get(name)) for name in HOOK_EVENTS):
        return {"status": "already wired"}

    wired = []
    for name in HOOK_EVENTS:
        entries = hooks_block.setdefault(name, [])
        if not _is_wired(entries):
            entries.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
        wired.append(name)

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    return {"wired": wired}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    try:
        event(payload)
    except Exception:
        pass
