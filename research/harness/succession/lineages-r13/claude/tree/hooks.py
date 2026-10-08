"""Agents: the coding-agent handshake (spec/layers.md's agents layer).

`event` turns one Claude Code hook payload into a trace event appended to
the session's draft trace (`authoring.TRACE`), the same file the authoring
layer reads to propose and certify a claim. It is guarded two ways: no
session (no `.reticuli` store under the payload's `cwd`) is a no-op, and a
tool path that resolves outside the session is ignored, never recorded.
Only `UserPromptSubmit` and the `PostToolUse` tool names this module knows
(`Write`, `Read`, `Bash`) map to anything; every other hook is a no-op.

A read event is recorded for its own sake -- a traced session should show
what it looked at -- but carries no `path`, so a read of a name that is not
yet a real file (a plan, a note the agent never produced) can never become
a declared pinned input that `authoring.build_claim` cannot find on disk.
Only a write's path (a candidate generated output) and a bash command's
own text (parsed for its redirect targets and decider tokens downstream)
carry a path-shaped value into the trace.

`install` wires `UserPromptSubmit` and `PostToolUse` into a project's
`.claude/settings.json`, preserving every other key, and is idempotent:
once both are wired to this module's command, a second call changes
nothing on disk.
"""
import json
import os
import time

from . import authoring

_SETTINGS_REL = os.path.join(".claude", "settings.json")
_HOOK_COMMAND = "python3 -m reticuli.hooks"
_WIRE_EVENTS = ("UserPromptSubmit", "PostToolUse")


# ------------------------------------------------------------- the trace --

def _session_root(cwd) -> str:
    if not cwd or not isinstance(cwd, str):
        return None
    if not os.path.isdir(os.path.join(cwd, ".reticuli")):
        return None
    return cwd


def _relpath(ws: str, abspath: str) -> str:
    """`abspath`'s path relative to `ws`, or `None` if it resolves outside."""
    if not abspath or not isinstance(abspath, str):
        return None
    rel = os.path.relpath(os.path.realpath(abspath), os.path.realpath(ws))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel.replace(os.sep, "/")


def _append(ws: str, entry: dict) -> None:
    path = os.path.join(ws, authoring.TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def event(payload: dict) -> dict:
    """One Claude Code hook payload, turned into a trace event and appended
    to the session's draft trace -- or `None` if there is no session, the
    hook is one this module does not map, or a tool's path escapes it."""
    if not isinstance(payload, dict):
        return None
    ws = _session_root(payload.get("cwd"))
    if ws is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "ts": time.time()}
        _append(ws, entry)
        return entry

    if name != "PostToolUse":
        return None

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool == "Write":
        rel = _relpath(ws, tool_input.get("file_path"))
        if rel is None:
            return None
        entry = {"event": "write", "path": rel, "ts": time.time()}
        _append(ws, entry)
        return entry

    if tool == "Read":
        rel = _relpath(ws, tool_input.get("file_path"))
        if rel is None:
            return None
        entry = {"event": "read", "ts": time.time()}
        _append(ws, entry)
        return entry

    if tool == "Bash":
        cmd = tool_input.get("command")
        if not cmd or not isinstance(cmd, str):
            return None
        entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
        _append(ws, entry)
        return entry

    return None


# -------------------------------------------------------------- wiring --

def _hook_wired(entries: list, command: str) -> bool:
    for group in entries or []:
        for h in (group or {}).get("hooks", []) or []:
            if h.get("type") == "command" and h.get("command") == command:
                return True
    return False


def install(proj: str) -> dict:
    """Wire `UserPromptSubmit` and `PostToolUse` into `proj`'s
    `.claude/settings.json`, preserving every other key and every other
    hook already wired there. Idempotent: once both are wired to this
    module's own command, a second call leaves the file untouched."""
    settings_path = os.path.join(proj, _SETTINGS_REL)
    if os.path.isfile(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_tbl = settings.get("hooks")
    if not isinstance(hooks_tbl, dict):
        hooks_tbl = {}

    wired = []
    for hook_name in _WIRE_EVENTS:
        entries = hooks_tbl.get(hook_name)
        if not isinstance(entries, list):
            entries = []
        if _hook_wired(entries, _HOOK_COMMAND):
            continue
        entries = entries + [{"hooks": [{"type": "command", "command": _HOOK_COMMAND}]}]
        hooks_tbl[hook_name] = entries
        wired.append(hook_name)

    if not wired:
        return {"status": "already wired"}

    settings["hooks"] = hooks_tbl
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f)
    return {"status": "wired", "wired": wired}


# ------------------------------------------------------------------- CLI --

if __name__ == "__main__":
    import sys

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = None
    event(payload)
