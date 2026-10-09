"""Agents: the coding-agent hook handshake (`spec/layers.md`).

`event(payload)` turns one Claude Code hook payload into a trace event,
appended to the session's draft trace (`reticuli.authoring.TRACE`) -- the
same file `reticuli.feedback.advise` and `reticuli.authoring.build_claim`
read. Guarded both ways: a payload whose `cwd` names no live session (no
`.reticuli` store there) is a no-op, and a `Write`/`Read` payload naming a
path outside that session is ignored rather than recorded under an
escaping name. Only `UserPromptSubmit` and `PostToolUse` (for `Write`,
`Read`, `Bash`) produce an event; every other hook name is a no-op.

`install(proj)` wires those two hooks into `proj`'s `.claude/settings.json`
as a command invoking this module, idempotently and without disturbing any
other key already in the file.

Stdlib only.
"""
import json
import os
import sys
import time

from reticuli import kernel
from reticuli.authoring import TRACE

_TOOL_EVENTS = {"Write": "write", "Read": "read", "Bash": "bash"}
_HOOK_NAMES = ("UserPromptSubmit", "PostToolUse")


def _session_dir(cwd):
    if cwd and os.path.isdir(os.path.join(cwd, kernel.STORE)):
        return cwd
    return None


def _relative(ws: str, path) -> str:
    """`path`'s location relative to `ws`, or `None` if it escapes it."""
    if not path:
        return None
    ws_real = os.path.realpath(ws)
    target = path if os.path.isabs(path) else os.path.join(ws, path)
    target_real = os.path.realpath(target)
    if target_real == ws_real:
        return None
    rel = os.path.relpath(target_real, ws_real)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, "/")


def _append(ws: str, fields: dict) -> dict:
    entry = {"ts": time.time(), **fields}
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def event(payload: dict):
    """One hook payload -> one appended trace event, or `None` for a no-op."""
    ws = _session_dir(payload.get("cwd"))
    if ws is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        return _append(ws, {"event": "prompt", "prompt": payload.get("prompt", "")})

    if name == "PostToolUse":
        tool_input = payload.get("tool_input") or {}
        kind = _TOOL_EVENTS.get(payload.get("tool_name"))
        if kind is None:
            return None
        if kind == "bash":
            cmd = tool_input.get("command")
            if not cmd:
                return None
            return _append(ws, {"event": "bash", "cmd": cmd})
        path = _relative(ws, tool_input.get("file_path"))
        if path is None:
            return None
        return _append(ws, {"event": kind, "path": path})

    return None


def install(proj: str) -> dict:
    """Wire `UserPromptSubmit`/`PostToolUse` into `proj`'s Claude Code
    settings, idempotently and without disturbing any other key there."""
    path = os.path.join(proj, ".claude", "settings.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    command = f"{sys.executable} -m reticuli.hooks"
    hooks_cfg = settings.setdefault("hooks", {})
    wired = []
    changed = False
    for hook_name in _HOOK_NAMES:
        entries = hooks_cfg.get(hook_name, [])
        present = any(h.get("command") == command
                      for entry in entries for h in entry.get("hooks", []))
        if not present:
            entries = entries + [{"hooks": [{"type": "command", "command": command}]}]
            hooks_cfg[hook_name] = entries
            changed = True
        wired.append(hook_name)

    if not changed:
        return {"status": "already wired", "wired": wired}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


if __name__ == "__main__":
    event(json.load(sys.stdin))
