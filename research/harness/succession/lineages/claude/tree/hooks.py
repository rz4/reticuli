"""reticuli.hooks -- the coding-agent handshake (`spec/layers.md`).

`event` turns one Claude Code hook payload into a trace entry appended to
the workspace's draft trace (the same file `reticuli.authoring` reads),
guarded two ways: a workspace with no `.reticuli` store is not a session,
so every payload is a no-op, and a tool payload naming a path outside the
session is ignored rather than traced. `install` wires this module into a
project's `.claude/settings.json` for `UserPromptSubmit` and `PostToolUse`,
idempotently and without disturbing anything else already in the file.

This module deliberately does not import `reticuli.authoring`: the agents
check imports `hooks` unconditionally, ahead of its own guarded import of
the authoring layer, so `hooks` must stay importable when that layer is
absent (`spec/layers.md`). `TRACE` below is the same path
`reticuli.authoring.TRACE` names, kept as its own literal for that reason.

Stdlib only. Never the network.
"""
import json
import os
import sys
import time

from . import kernel

TRACE = ".reticuli/draft.jsonl"

_HOOK_COMMAND = "python3 -m reticuli.hooks"
_WIRED_EVENTS = ("UserPromptSubmit", "PostToolUse")
_PATH_EVENTS = {"Write": "write", "Edit": "write", "Read": "read"}


def _is_session(cwd) -> bool:
    return isinstance(cwd, str) and bool(cwd) and os.path.isdir(os.path.join(cwd, kernel.STORE))


def _relative_inside(cwd: str, path: str):
    """`path` relative to `cwd`, or `None` if it does not resolve inside it."""
    cwd_real = os.path.realpath(cwd)
    path_real = os.path.realpath(path)
    if path_real != cwd_real and not path_real.startswith(cwd_real + os.sep):
        return None
    return os.path.relpath(path_real, cwd_real)


def _append_trace(cwd: str, entry: dict) -> None:
    path = os.path.join(cwd, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def event(payload: dict):
    """Map one hook payload to a trace entry, and append it to the
    session's trace. `None` when the payload is not a session event: no
    `.reticuli` store at `cwd` (no session), an unrecognized hook or tool
    name, or a tool path that resolves outside the session."""
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not _is_session(cwd):
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "prompt": payload.get("prompt", ""), "ts": time.time()}
    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        if tool in _PATH_EVENTS:
            path = tool_input.get("file_path")
            if not isinstance(path, str) or not path:
                return None
            rel = _relative_inside(cwd, path)
            if rel is None:
                return None
            entry = {"event": _PATH_EVENTS[tool], "path": rel, "ts": time.time()}
        elif tool == "Bash":
            cmd = tool_input.get("command")
            if not isinstance(cmd, str) or not cmd:
                return None
            entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
        else:
            return None
    else:
        return None

    _append_trace(cwd, entry)
    return entry


def _has_our_hook(entries) -> bool:
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hooks", []):
            if isinstance(h, dict) and h.get("command") == _HOOK_COMMAND:
                return True
    return False


def install(proj: str) -> dict:
    """Wire this module into `proj`'s `.claude/settings.json` for every
    event in `_WIRED_EVENTS`, idempotently -- an event already wired to
    this module's command is left untouched, and every other key already
    in the file survives byte-for-byte when nothing changes."""
    settings_path = os.path.join(proj, ".claude", "settings.json")
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise kernel.ClaimError(f"malformed settings at {settings_path!r}: not an object")

    hooks_cfg = settings.get("hooks")
    if not isinstance(hooks_cfg, dict):
        hooks_cfg = {}

    wired = []
    for event_name in _WIRED_EVENTS:
        entries = hooks_cfg.get(event_name)
        if _has_our_hook(entries):
            continue
        entries = list(entries) if isinstance(entries, list) else []
        entries.append({"hooks": [{"type": "command", "command": _HOOK_COMMAND}]})
        hooks_cfg[event_name] = entries
        wired.append(event_name)

    if not wired:
        return {"status": "already wired", "wired": []}

    settings["hooks"] = hooks_cfg
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "installed", "wired": wired}


def main() -> None:
    """Entry point for the wired hook command: read one JSON payload from
    stdin, trace it if it is a session event, and always exit clean --
    a hook failure must never block the agent's tool call."""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, TypeError):
        return
    try:
        event(payload)
    except kernel.ClaimError:
        pass


if __name__ == "__main__":
    main()
