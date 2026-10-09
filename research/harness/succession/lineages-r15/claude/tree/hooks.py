"""agents: the coding-agent handshake (`spec/layers.md`).

Claude Code (or any compatible agent) calls out to a hook on each event; a
hook payload carries `hook_event_name`, a `cwd`, and event-specific fields
(`prompt`, `tool_name`, `tool_input`). `event` turns the payloads that
matter -- a prompt, a file write, a file read, a shell command -- into the
same trace format `reticuli.authoring` already reads (`TRACE`,
`spec/layers.md`'s authoring layer): one JSON object per line, `event` plus
`prompt`/`path`/`cmd`. A payload is a no-op, not an error, when its `cwd`
names no session (no `.reticuli` store there yet) or when a traced path
escapes the session root -- the session's trace never records what happens
outside it.

`install` wires an agent's own settings (`.claude/settings.json`) to call
this module's hook for the two event kinds the trace needs, idempotently
and without disturbing any other key already in the file.

Stdlib only.
"""
import json
import os
import sys
import time

from reticuli import kernel
from reticuli._util import trace_append
from reticuli.authoring import TRACE

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_READ_TOOLS = frozenset({"Read"})
_BASH_TOOLS = frozenset({"Bash"})

HOOK_COMMAND = f"{sys.executable} -c " \
    "\"import json,sys; from reticuli import hooks; hooks.event(json.load(sys.stdin))\""


def _session_root(cwd):
    """The realpath of `cwd` if a reticuli session has started there
    (its store directory exists), else None -- a payload from anywhere
    else is a no-op.
    """
    if not cwd:
        return None
    root = os.path.realpath(cwd)
    if not os.path.isdir(os.path.join(root, kernel.STORE)):
        return None
    return root


def _relative(session_root: str, file_path):
    """`file_path` relative to `session_root`, or None when it is missing
    or resolves outside the session -- a tool acting elsewhere is not part
    of this session's trace.
    """
    if not file_path:
        return None
    if not os.path.isabs(file_path):
        file_path = os.path.join(session_root, file_path)
    resolved = os.path.realpath(file_path)
    if resolved != session_root and not resolved.startswith(session_root + os.sep):
        return None
    return os.path.relpath(resolved, session_root)


def _record(session_root: str, entry: dict) -> dict:
    entry = dict(entry)
    entry.setdefault("ts", time.time())
    trace_append(os.path.join(session_root, TRACE), entry)
    return entry


def event(payload: dict):
    """One hook payload, turned into a trace event -- or None when the
    payload is not part of any session's trace.
    """
    session_root = _session_root(payload.get("cwd"))
    if session_root is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        return _record(session_root, {"event": "prompt", "prompt": payload.get("prompt", "")})

    if name != "PostToolUse":
        return None

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool in _WRITE_TOOLS or tool in _READ_TOOLS:
        rel = _relative(session_root, tool_input.get("file_path"))
        if rel is None:
            return None
        kind = "write" if tool in _WRITE_TOOLS else "read"
        return _record(session_root, {"event": kind, "path": rel})

    if tool in _BASH_TOOLS:
        cmd = tool_input.get("command")
        if not cmd:
            return None
        return _record(session_root, {"event": "bash", "cmd": cmd})

    return None


# -- install: wire an agent's settings to call `event` on the two hook
# kinds the trace needs, idempotently, preserving every other key. -------


def _already_wired(entries) -> bool:
    for entry in entries or []:
        for h in entry.get("hooks", []):
            if h.get("command") == HOOK_COMMAND:
                return True
    return False


def install(proj: str) -> dict:
    """Wire `proj`'s `.claude/settings.json` to call this module's hook
    on `UserPromptSubmit` and `PostToolUse`. Idempotent: a settings file
    already wired is returned untouched, byte for byte, and every other
    key -- present before this call or added by someone else since -- is
    preserved either way.
    """
    settings_path = os.path.join(proj, ".claude", "settings.json")
    settings = {}
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

    hooks_cfg = settings.get("hooks", {})
    events = ("UserPromptSubmit", "PostToolUse")

    if all(_already_wired(hooks_cfg.get(ev)) for ev in events):
        return {"status": "already wired", "wired": []}

    wired = []
    for ev in events:
        entries = hooks_cfg.setdefault(ev, [])
        if _already_wired(entries):
            continue
        entries.append({"matcher": "", "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
        wired.append(ev)

    settings["hooks"] = hooks_cfg
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


if __name__ == "__main__":
    event(json.load(sys.stdin))
