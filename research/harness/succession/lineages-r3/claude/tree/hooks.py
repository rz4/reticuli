"""Agents: the coding-agent handshake (spec/layers.md, "agents").

`event` turns one Claude Code hook payload into a trace event appended
to the session's draft trace (`.reticuli/draft.jsonl`) -- the same file
`authoring.propose` and `feedback.advise` already read: `prompt`,
`write`, `read`, and `bash` events. A payload names its session only
through its own `cwd` -- no `.reticuli` store there means no session,
and the payload is a no-op; a tool payload whose file falls outside the
session is ignored the same way. Every other hook name (anything this
layer does not trace) maps to nothing.

`install` idempotently wires `UserPromptSubmit` and `PostToolUse` into a
Claude Code project's `.claude/settings.json`, through this module's own
command so a second call changes nothing on disk and every other key
already in the file survives untouched.
"""
import json
import os
import sys
import time

from reticuli import kernel

TRACE = f"{kernel.STORE}/draft.jsonl"
SETTINGS = os.path.join(".claude", "settings.json")
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
COMMAND = f"{sys.executable} -m reticuli.hooks"


# ===========================================================================
# event: one hook payload -> one appended trace line, or None.
# ===========================================================================


def _session_ws(cwd):
    """`cwd` itself, if it carries a `.reticuli` store -- the one
    directory-entry fact that decides whether a payload belongs to a
    session at all.
    """
    if not isinstance(cwd, str) or not cwd:
        return None
    if not os.path.isdir(os.path.join(cwd, kernel.STORE)):
        return None
    return cwd


def _relative(ws: str, path) -> str:
    """`path`'s POSIX-separated path relative to `ws`, or `None` if
    `path` is not a string or resolves outside `ws` -- the session
    boundary a traced file event must respect.
    """
    if not isinstance(path, str) or path == "":
        return None
    ws_real = os.path.realpath(ws)
    full = path if os.path.isabs(path) else os.path.join(ws_real, path)
    real = os.path.realpath(full)
    if real != ws_real and not real.startswith(ws_real + os.sep):
        return None
    return os.path.relpath(real, ws_real).replace(os.sep, "/")


def _append(ws: str, entry: dict) -> None:
    path = os.path.join(ws, *TRACE.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def event(payload: dict):
    """One Claude Code hook payload turned into one appended trace
    event, returned as that event's dict -- or `None` when the payload
    is not traced.
    """
    if not isinstance(payload, dict):
        return None
    ws = _session_ws(payload.get("cwd"))
    if ws is None:
        return None

    name = payload.get("hook_event_name")

    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "ts": time.time()}
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            entry["prompt"] = prompt
        _append(ws, entry)
        return entry

    if name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input") or {}

        if tool == "Bash":
            cmd = tool_input.get("command")
            if not isinstance(cmd, str):
                return None
            entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
            _append(ws, entry)
            return entry

        if tool in ("Write", "Edit"):
            rel = _relative(ws, tool_input.get("file_path"))
            if rel is None:
                return None
            entry = {"event": "write", "path": rel, "ts": time.time()}
            _append(ws, entry)
            return entry

        if tool == "Read":
            rel = _relative(ws, tool_input.get("file_path"))
            if rel is None:
                return None
            entry = {"event": "read", "path": rel, "ts": time.time()}
            _append(ws, entry)
            return entry

        return None

    return None


# ===========================================================================
# install: idempotent Claude Code settings wiring.
# ===========================================================================


def _hook_entry(name: str) -> dict:
    entry = {"hooks": [{"type": "command", "command": COMMAND}]}
    if name == "PostToolUse":
        entry["matcher"] = "*"
    return entry


def _already_wired(entries) -> bool:
    for entry in entries or []:
        for h in entry.get("hooks", []):
            if h.get("type") == "command" and h.get("command") == COMMAND:
                return True
    return False


def install(project: str) -> dict:
    """Idempotently wire `UserPromptSubmit` and `PostToolUse` into
    `project`'s `.claude/settings.json`. A second call recognizes this
    module's own command already present and makes no change at all;
    every other key in the file -- and the file's bytes, when nothing
    was missing -- survives untouched.
    """
    path = os.path.join(project, SETTINGS)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.get("hooks", {})
    missing = [name for name in HOOK_EVENTS if not _already_wired(hooks_cfg.get(name))]

    if not missing:
        return {"status": "already wired", "wired": []}

    for name in missing:
        hooks_cfg.setdefault(name, []).append(_hook_entry(name))
    settings["hooks"] = hooks_cfg

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, sort_keys=True, indent=2)

    return {"status": "wired", "wired": missing}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    event(payload)
