"""The coding-agent handshake: Claude Code hook payloads become trace events.

`event(payload)` maps one hook invocation (Claude Code's shape: a JSON
object naming `hook_event_name`, `cwd`, and event-specific fields) to the
authoring layer's trace format and appends it to the session's trace
(`reticuli/authoring.py`'s `TRACE`, `.reticuli/draft.jsonl`). Guarded: a
`cwd` that is not a session (no `.reticuli` directory) is a no-op, and a
file path outside the session is ignored -- both return `None`. A file
event naming a path that does not exist in the session yet is still
reported back to the caller (a hook fires once per tool call, and the
caller may want to know what happened), but it is not written to the
trace -- a path the session does not yet hold is not evidence of
anything `build_claim` should classify.

`install(proj)` wires the two hook events a session's trace needs into a
project's `.claude/settings.json`: idempotent, and it never touches
anything else already in that file.

Stdlib only.
"""
import json
import os
import sys

from reticuli import kernel
from . import _util

TRACE = f"{kernel.STORE}/draft.jsonl"
SETTINGS = os.path.join(".claude", "settings.json")
_WIRED_EVENTS = ("UserPromptSubmit", "PostToolUse")


def _is_session(cwd) -> bool:
    return bool(cwd) and os.path.isdir(os.path.join(cwd, kernel.STORE))


def _rel_inside(cwd: str, path: str):
    """`path` relative to `cwd`, or None if it does not resolve inside it."""
    cwd_real = os.path.realpath(cwd)
    path_real = os.path.realpath(path)
    if path_real != cwd_real and not path_real.startswith(cwd_real + os.sep):
        return None
    rel = os.path.relpath(path_real, cwd_real)
    return rel.replace(os.sep, "/")


def _map(payload: dict, cwd: str):
    """The trace entry a payload names, or None if it names none."""
    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        return {"event": "prompt", "prompt": payload.get("prompt", "")}

    if name != "PostToolUse":
        return None
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = tool_input.get("command")
        return {"event": "bash", "cmd": cmd} if cmd else None

    if tool in ("Write", "Read"):
        file_path = tool_input.get("file_path")
        if not file_path:
            return None
        rel = _rel_inside(cwd, file_path)
        if rel is None:
            return None
        return {"event": "write" if tool == "Write" else "read", "path": rel}

    return None


def event(payload: dict):
    """Map one hook payload to a trace event and record it. Returns the
    event dict, or None if the payload names no session or no event."""
    cwd = payload.get("cwd")
    if not _is_session(cwd):
        return None

    entry = _map(payload, cwd)
    if entry is None:
        return None

    if entry["event"] in ("write", "read"):
        if not os.path.isfile(os.path.join(cwd, entry["path"])):
            return entry

    _util.locked_append(os.path.join(cwd, TRACE), json.dumps(entry, sort_keys=True))
    return entry


# -- wiring: the agent-side half of the handshake -----------------------------


def install(proj: str) -> dict:
    """Wire the trace hooks into `proj`'s `.claude/settings.json`.

    Idempotent: a project already wired for every event in `_WIRED_EVENTS`
    is left untouched -- byte for byte -- and everything else the file
    already holds survives either way.
    """
    path = os.path.join(proj, SETTINGS)
    settings = _util.read_json(path) if os.path.isfile(path) else {}

    hooks_cfg = settings.get("hooks", {})
    if all(ev in hooks_cfg for ev in _WIRED_EVENTS):
        return {"status": "already wired", "wired": sorted(hooks_cfg.keys())}

    command = f"{sys.executable} -m reticuli.hooks"
    for ev in _WIRED_EVENTS:
        if ev not in hooks_cfg:
            hooks_cfg[ev] = [{"hooks": [{"type": "command", "command": command}]}]
    settings["hooks"] = hooks_cfg

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": sorted(_WIRED_EVENTS)}


# -- entry point when run as the hook command ---------------------------------


def main() -> None:
    payload = json.load(sys.stdin)
    event(payload)


if __name__ == "__main__":
    main()
