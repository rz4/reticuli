"""The coding-agent handshake: payloads become observations.

An agent harness emits a payload per event; this translates one into a trace
event, or into nothing.  "Nothing" is most of the contract:

* **no session, no-op** — a payload whose `cwd` is not an initialized
  workspace is ignored, so wiring the hooks globally cannot scatter traces
  across a machine;
* **outside the session is ignored** — a file the agent touched elsewhere is
  not part of this session's observations, and recording it would propose an
  input the claim could never confine;
* **an event this handshake does not model is nothing**, rather than a guess.

Wiring is **idempotent and preserving**: installing twice changes no bytes,
and everything else in the agent's settings survives untouched.  A tool that
rewrote a user's configuration to add itself would be a worse citizen than
one that refused.
"""
import json
import os

from . import _util, kernel

#: Where an agent's project configuration lives, per agent.
SETTINGS = {"claude": os.path.join(".claude", "settings.json")}
#: The events this handshake models.
WIRED = ("UserPromptSubmit", "PostToolUse")
#: Tool names, mapped to the observation each one is.
_TOOLS = {"Write": "write", "Edit": "write", "MultiEdit": "write",
          "NotebookEdit": "write", "Read": "read", "Bash": "bash"}


def _inside(workspace: str, path: str):
    """The path relative to the session, or None if it is outside it."""
    if not path:
        return None
    base = os.path.realpath(workspace)
    target = os.path.realpath(
        path if os.path.isabs(path) else os.path.join(workspace, path))
    if target == base or not target.startswith(base + os.sep):
        return None
    return os.path.relpath(target, base).replace(os.sep, "/")


def _translate(payload: dict, session: str, stamp: str):
    kind = payload.get("hook_event_name")
    if kind == "UserPromptSubmit":
        return {"event": "prompt", "text": payload.get("prompt") or "",
                "via": "hook", "when": stamp}
    if kind != "PostToolUse":
        return None                       # an unmodelled event is nothing
    action = _TOOLS.get(payload.get("tool_name"))
    if action is None:
        return None
    arguments = payload.get("tool_input") or {}
    if action == "bash":
        command = arguments.get("command")
        if not command:
            return None
        return {"event": "bash", "cmd": command, "via": "hook",
                "when": stamp}
    relative = _inside(session, arguments.get("file_path")
                       or arguments.get("path"))
    if relative is None:
        return None                       # outside the session is ignored
    return {"event": action, "path": relative, "via": "hook", "when": stamp}


def event(payload: dict, workspace: str = None):
    """Translate one hook payload into a trace event and record it.

    Translating and recording are one act on purpose: the handshake's whole
    job is to turn a payload into an observation the session keeps, and an
    `event` that returned without recording would be a function whose only
    caller has to remember the second half.
    """
    if not isinstance(payload, dict):
        return None
    session = workspace or payload.get("cwd") or os.getcwd()
    if not os.path.isdir(os.path.join(session, kernel.STORE)):
        return None                       # no session, no-op
    stamp = _util.stamp()
    recorded = _translate(payload, session, stamp)
    if recorded is None:
        return None
    transcript = payload.get("transcript_path")
    if transcript and recorded["event"] == "prompt":
        # The harness's own usage records are where a discovery bill can be
        # priced later; remembering the path is cheaper and more honest than
        # copying the numbers now.  Recorded BEFORE the prompt, so the
        # prompt stays the session's latest word.
        _util.trace_append(session, {"event": "session",
                                     "transcript": transcript,
                                     "via": "hook", "when": stamp})
    _util.trace_append(session, recorded)
    return recorded


def observe(payload: dict, workspace: str = None):
    """`event`, under the name a caller driving the handshake may prefer."""
    return event(payload, workspace)


def install(project: str, agent: str = "claude") -> dict:
    """Wire the handshake into an agent's project settings, idempotently."""
    relative = SETTINGS.get(agent)
    if relative is None:
        raise kernel.ClaimError(
            f"unsupported agent {agent!r}; known: "
            f"{', '.join(sorted(SETTINGS))}")
    path = os.path.join(project, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    settings = _util.read_json(path, {}) or {}
    if not isinstance(settings, dict):
        raise kernel.ClaimError(f"{path}: the agent's settings are not an "
                                f"object; refusing to rewrite them")
    command = "ret hook"
    hooks = settings.setdefault("hooks", {})
    wired, already = [], True
    for name in WIRED:
        entries = hooks.setdefault(name, [])
        if any(command in json.dumps(entry) for entry in entries):
            wired.append(name)
            continue
        entries.append({"hooks": [{"type": "command", "command": command}]})
        wired.append(name)
        already = False
    if already:
        return {"status": "already wired", "wired": wired, "settings": path}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"status": "wired", "wired": wired, "settings": path}
