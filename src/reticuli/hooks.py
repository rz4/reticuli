"""The agent handshake: a coding agent's hook events become the session trace.

A harness calls `ret hook` with a JSON payload on stdin at each event; the
payload maps to a draft event — prompt, write, read, or bash — appended to the
session's trace. Two adapters read the payload:

  * the **generic** adapter accepts reticuli's own event shape directly
    (`{"event": "write"|"read"|"bash"|"prompt", ...}`), so any harness can
    integrate by emitting that, no special case here;
  * the **Claude Code** adapter maps that product's hook vocabulary
    (`hook_event_name`, `tool_name`, `tool_input`, ...) — another product's
    API, not ours, and the most volatile interface in the system.

`ret init` wires the harness it knows (Claude Code) idempotently; for any other
harness, `ret init --agent generic` sets up the workspace and the harness is
pointed at the generic contract above.

This module only translates and appends — every decision that can be made below
it is made below it. A hook fires only inside a session (a .reticuli/ store
exists); everywhere else it is a silent no-op, because an agent's hook must
never fail in a directory that has nothing to do with us.
"""
from __future__ import annotations

import json
import os
import shlex
import sys

from . import _util, kernel

WRITES = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
READS = frozenset({"Read"})


def _canonical(payload: dict) -> dict | None:
    """The generic adapter: a harness speaking reticuli's own event shape. This
    is the documented contract any harness can target without a special case —
    `{"event": "prompt", "text": ...}`, `{"event": "bash", "cmd": ...}`, or
    `{"event": "write"|"read", "path": ...}`. Paths are confined below."""
    kind = payload.get("event")
    if kind == "prompt" and payload.get("text"):
        return {"event": "prompt", "text": payload["text"]}
    if kind == "bash" and payload.get("cmd"):
        return {"event": "bash", "cmd": payload["cmd"]}
    if kind in ("write", "read") and payload.get("path"):
        return {"event": kind, "path": payload["path"]}
    return None


def _claude(payload: dict) -> dict | None:
    """The Claude Code adapter: its hook vocabulary, matched literally. These
    keys and names are that product's API, so they are never renamed here."""
    name = payload.get("hook_event_name", "")
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    if name == "UserPromptSubmit" and payload.get("prompt"):
        return {"event": "prompt", "text": payload["prompt"]}
    if name == "PostToolUse" and tool == "Bash" and tin.get("command"):
        return {"event": "bash", "cmd": tin["command"]}
    if name == "PostToolUse" and tool in WRITES | READS and tin.get("file_path"):
        return {"event": "write" if tool in WRITES else "read",
                "path": tin["file_path"]}
    return None


#: Tried in order: the native shape first, then the Claude Code vocabulary. A
#: new harness that cannot emit the generic shape gets its own adapter here.
ADAPTERS = (_canonical, _claude)


def event(payload: dict, workspace: str | None = None) -> dict | None:
    """Map one hook payload to a draft event and append it; None if it isn't
    one (unknown event, file outside the session, or no session at all)."""
    ws = os.path.abspath(workspace or payload.get("cwd") or ".")
    if not os.path.isdir(os.path.join(ws, kernel.STORE)):
        return None                                    # not a session — no-op
    ev = None
    for adapt in ADAPTERS:
        ev = adapt(payload)
        if ev is not None:
            break
    if ev is None:
        return None
    if ev["event"] in ("write", "read"):
        raw = ev["path"]
        target = raw if os.path.isabs(raw) else os.path.join(ws, raw)
        rel = os.path.relpath(os.path.abspath(target), ws)
        if rel.startswith(".."):
            return None                                # outside the session
        ev["path"] = rel.replace(os.sep, "/")
    ev["via"] = "hook"                  # the observation's provenance
    trace = os.path.join(ws, kernel.STORE, "draft.jsonl")
    # The harness names its own transcript in every payload. Remember it once
    # as session meta: at pack time the authoring layer reads the transcript's
    # USAGE entries -- never message content -- so the claim's C1 can carry
    # what the discovery session actually cost, as the harness testifies it.
    transcript = payload.get("transcript_path")
    if transcript:
        known = ""
        try:
            with open(trace, encoding="utf-8") as f:
                known = f.read()
        except OSError:
            pass
        if f'"transcript": "{transcript}"' not in known:
            _util.trace_append(trace, {"event": "session",
                                       "transcript": transcript, "via": "hook"})
    _util.trace_append(trace, ev)       # stamped + lock-serialized (swarm-safe)
    return ev


def consume(workspace: str | None = None) -> dict:
    """`ret hook`: read one payload from stdin, append its event. Never raises,
    never blocks the agent — a malformed payload is simply not a trace event."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    ev = event(payload if isinstance(payload, dict) else {}, workspace)
    return {"traced": ev is not None, "event": ev["event"] if ev else None}


# The event names below are the Claude Code harness's vocabulary, not ours:
# matched literally against what it sends, so never renamed by us.
EVENTS = {"UserPromptSubmit": None,
          "PostToolUse": "Write|Edit|MultiEdit|NotebookEdit|Read|Bash"}


def _hook_command() -> str:
    """The command a harness runs at each event: this interpreter's own module
    form, by absolute path.

    A bare `ret hook` is what this deliberately avoids. `ret` on PATH at init
    time is no guarantee `ret` is on PATH when the harness fires the hook — a
    venv install (the documented path) puts `ret` on PATH only while the venv is
    active, so a bare wiring silently no-ops the moment it is not, and every
    event is lost without a word. `{sys.executable} -m reticuli hook` names the
    exact interpreter that ran init — absolute, PATH-independent, and the same
    reticuli that will read the trace — so it resolves whenever that install
    exists at all."""
    return f"{shlex.quote(sys.executable)} -m reticuli hook"


def _is_reticuli_hook(command: str) -> bool:
    """Whether a wired hook command is one of ours, in any install form, so
    re-running init across environments recognizes an existing wiring instead
    of appending a duplicate."""
    return command == "ret hook" or command.rstrip().endswith("reticuli hook")


def install(project: str) -> dict:
    """`ret hooks`: wire the Claude Code harness to the trace via
    .claude/settings.json. Idempotent — merges the two entries in, touches
    nothing else — and wires a command form that works in this environment."""
    root = os.path.abspath(project)
    path = os.path.join(root, ".claude", "settings.json")
    settings = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    hook = {"type": "command", "command": _hook_command()}
    hooks = settings.setdefault("hooks", {})
    wired = []
    for name, matcher in EVENTS.items():
        entries = hooks.setdefault(name, [])
        if not any(_is_reticuli_hook(h.get("command", ""))
                   for e in entries for h in e.get("hooks", [])):
            entry = {"matcher": matcher, "hooks": [dict(hook)]} if matcher \
                else {"hooks": [dict(hook)]}
            entries.append(entry)
            wired.append(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"settings": os.path.join(".claude", "settings.json"),
            "wired": wired, "command": hook["command"],
            "status": "wired" if wired else "already wired"}
