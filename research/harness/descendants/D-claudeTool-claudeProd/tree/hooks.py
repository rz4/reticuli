"""The coding-agent handshake.

An agent harness announces what it did; this turns those announcements into
trace events a session can later be sealed from. Guarded on both sides: no
session means no-op, and a file outside the session is not this session's
business. Wiring is idempotent and leaves the rest of the agent's settings
exactly as it found them.
"""
import json
import os

from ._util import STORE, read_json, safe_path, trace_append, write_json

#: The payload events this handshake understands.
PROMPT = "UserPromptSubmit"
TOOL = "PostToolUse"

#: Which tool means which observation.
_TOOLS = {"Write": "write", "Edit": "write", "MultiEdit": "write",
          "NotebookEdit": "write", "Read": "read", "Bash": "bash"}

#: The hook events the wiring installs.
WIRED = ("UserPromptSubmit", "PostToolUse")


def _session(payload: dict):
    """The workspace this payload belongs to, if it is a session at all."""
    cwd = payload.get("cwd")
    if not cwd or not os.path.isdir(os.path.join(cwd, STORE)):
        return None
    return cwd


def event(payload: dict):
    """One harness payload as a trace event -- or None, which is a no-op."""
    if not isinstance(payload, dict):
        return None
    ws = _session(payload)
    if ws is None:
        return None
    kind = payload.get("hook_event_name")
    if kind == PROMPT:
        transcript = payload.get("transcript_path")
        if transcript:
            trace_append(ws, {"event": "session", "transcript": transcript,
                              "via": "hook"})
        return trace_append(ws, {"event": "prompt",
                                 "text": payload.get("prompt") or "",
                                 "via": "hook"})
    if kind != TOOL:
        return None
    observation = _TOOLS.get(payload.get("tool_name") or "")
    if observation is None:
        return None
    tool_input = payload.get("tool_input") or {}
    if observation == "bash":
        command = tool_input.get("command")
        if not command:
            return None
        return trace_append(ws, {"event": "bash", "cmd": command,
                                 "via": "hook"})
    where = tool_input.get("file_path") or tool_input.get("path")
    if not where:
        return None
    absolute = where if os.path.isabs(where) else os.path.join(ws, where)
    relative = os.path.relpath(absolute, ws)
    if safe_path(ws, relative) is None:
        return None                      # outside the session: not ours
    return trace_append(ws, {"event": observation, "path": relative,
                             "via": "hook"})


def _command(project: str) -> str:
    return f"ret hook -C {project}"


def install(project: str, agent: str = "claude") -> dict:
    """Wire the handshake into an agent's settings, idempotently."""
    if agent != "claude":
        raise ValueError(f"unsupported agent: {agent}")
    folder = os.path.join(project, ".claude")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "settings.json")
    settings = read_json(path, {})
    if not isinstance(settings, dict):
        settings = {}
    command = _command(project)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    changed = []
    for name in WIRED:
        entries = hooks.get(name)
        if not isinstance(entries, list):
            entries = []
        already = any(
            isinstance(entry, dict)
            and any(isinstance(inner, dict) and inner.get("command") == command
                    for inner in (entry.get("hooks") or []))
            for entry in entries)
        if already:
            continue
        entries.append({"hooks": [{"type": "command", "command": command}]})
        hooks[name] = entries
        changed.append(name)
    if not changed:
        return {"status": "already wired", "wired": list(WIRED),
                "settings": path}
    settings["hooks"] = hooks
    write_json(path, settings)
    return {"status": "wired", "wired": changed, "settings": path}


def payload_from(stream) -> dict:
    """Read one JSON payload from a stream; a damaged one is a no-op."""
    try:
        text = stream.read()
    except (OSError, ValueError):
        return {}
    if not text or not text.strip():
        return {}
    try:
        document = json.loads(text)
    except ValueError:
        return {}
    return document if isinstance(document, dict) else {}
