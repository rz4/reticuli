"""The coding-agent handshake.

An agent harness emits hook payloads; this layer turns the ones that matter
into trace events and ignores the rest. Three guards, and all three are
about not inventing history:

  * NO SESSION, NO-OP. A payload whose working directory is not an
    initialized workspace writes nothing. A hook that created sessions
    wherever it fired would seal whatever happened to be on the disk.
  * OUTSIDE THE SESSION IS IGNORED. A write to a path above the workspace
    is not this session's work, and a trace that recorded it would propose
    an input the claim cannot contain.
  * THE WIRING IS IDEMPOTENT. Installing twice changes nothing, and
    everything else in the agent's settings survives untouched -- a tool
    that rewrote a user's configuration to install itself would be
    unwelcome whatever else it got right.
"""
import json
import os

from . import _util
from .authoring import TRACE

#: the payload field each harness event carries its subject in
WRITERS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
READERS = ("Read", "NotebookRead")
EVENTS = ("UserPromptSubmit", "PostToolUse")
WIRED = ("UserPromptSubmit", "PostToolUse")
SETTINGS = os.path.join(".claude", "settings.json")
COMMAND = "python3 -m reticuli hook"


def _session(payload: dict):
    """The workspace this payload belongs to, if it is one at all."""
    where = payload.get("cwd") or os.getcwd()
    if not os.path.isdir(os.path.join(where, _util.STORE)):
        return None
    return where


def _inside(ws: str, path: str):
    """The path, relative to the session -- or None if it is not in it."""
    if not path:
        return None
    absolute = path if os.path.isabs(path) else os.path.join(ws, path)
    base = os.path.realpath(ws)
    here = os.path.realpath(absolute)
    if here != base and not here.startswith(base + os.sep):
        return None
    return os.path.relpath(here, base).replace(os.sep, "/")


def event(payload: dict):
    """One hook payload as a trace event, or None if it is not one.

    The event is appended to the session's trace as it is returned: the
    handshake is the writing, and a caller that only wanted the shape can
    read the return value.
    """
    if not isinstance(payload, dict):
        return None
    ws = _session(payload)
    if ws is None:
        return None
    kind = payload.get("hook_event_name")
    if kind not in EVENTS:
        return None
    found = None
    if kind == "UserPromptSubmit":
        text = payload.get("prompt")
        if not isinstance(text, str):
            return None
        found = {"event": "prompt", "text": text}
    else:
        tool = payload.get("tool_name")
        given = payload.get("tool_input") or {}
        if tool in WRITERS or tool in READERS:
            inside = _inside(ws, given.get("file_path") or
                             given.get("notebook_path") or "")
            if inside is None:
                return None
            found = {"event": "write" if tool in WRITERS else "read",
                     "path": inside}
        elif tool == "Bash":
            command = given.get("command")
            if not isinstance(command, str) or not command.strip():
                return None
            found = {"event": "bash", "cmd": command}
        else:
            return None
    found["ts"] = _ts()
    found["via"] = "hook"
    path = os.path.join(ws, TRACE)
    transcript = payload.get("transcript_path")
    if transcript:
        # the harness's own usage records, remembered as session meta so the
        # discovery bill can be priced later from what the harness reported
        _util.trace_append(path, {"event": "session",
                                  "transcript": transcript,
                                  "ts": found["ts"], "via": "hook"})
    _util.trace_append(path, found)
    return found


def _ts() -> float:
    import time
    return round(time.time(), 3)


def install(project: str, agent: str = "claude") -> dict:
    """Wire the hooks into an agent's settings, without touching the rest."""
    if agent not in ("claude",):
        raise ValueError(f"unsupported agent: {agent}")
    path = os.path.join(project, SETTINGS)
    settings = _util.read_json(path, default={}) or {}
    if not isinstance(settings, dict):
        settings = {}
    hooks = settings.get("hooks")
    hooks = dict(hooks) if isinstance(hooks, dict) else {}

    def already(name: str) -> bool:
        for entry in hooks.get(name) or []:
            for inner in (entry.get("hooks") or []) \
                    if isinstance(entry, dict) else []:
                if COMMAND in str(inner.get("command", "")):
                    return True
        return False

    wired = []
    for name in WIRED:
        if already(name):
            continue
        hooks.setdefault(name, []).append(
            {"matcher": "*", "hooks": [{"type": "command",
                                        "command": COMMAND}]})
        wired.append(name)
    if not wired:
        return {"status": "already wired", "wired": list(WIRED),
                "settings": path}
    settings["hooks"] = hooks
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"status": "wired", "wired": wired, "settings": path}
