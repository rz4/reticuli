"""The agent handshake: a coding agent's hook events become the session trace.

Claude Code (and compatible harnesses) call `ret hook` with a JSON payload on
stdin at each event; the payload maps to a draft event — prompt, write, read,
or bash — appended to the session's trace. `ret hooks` wires the project's
agent settings, idempotently.

This is the most volatile interface in the system, and deliberately the
thinnest one. The payload keys and the event names it matches on are another
product's API, not ours: they change when that product changes, and no amount
of care here prevents that. So this module only translates and appends —
every decision that can be made below it is made below it. A hook fires only
inside a session (a .reticuli/ store exists); everywhere else it is a silent
no-op, because an agent's hook must never fail in a directory that has
nothing to do with us.
"""
from __future__ import annotations

import json
import os
import sys
import time

from . import kernel

WRITES = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
READS = frozenset({"Read"})


def event(payload: dict, workspace: str | None = None) -> dict | None:
    """Map one hook payload to a draft event and append it; None if it isn't
    one (unknown event, file outside the session, or no session at all)."""
    ws = os.path.abspath(workspace or payload.get("cwd") or ".")
    if not os.path.isdir(os.path.join(ws, kernel.STORE)):
        return None                                    # not a session — no-op
    name = payload.get("hook_event_name", "")
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    ev = None
    if name == "UserPromptSubmit" and payload.get("prompt"):
        ev = {"event": "prompt", "text": payload["prompt"]}
    elif name == "PostToolUse" and tool == "Bash" and tin.get("command"):
        ev = {"event": "bash", "cmd": tin["command"]}
    elif name == "PostToolUse" and tool in WRITES | READS and tin.get("file_path"):
        rel = os.path.relpath(os.path.abspath(tin["file_path"]), ws)
        if rel.startswith(".."):
            return None                                # outside the session
        ev = {"event": "write" if tool in WRITES else "read",
              "path": rel.replace(os.sep, "/")}
    if ev is None:
        return None
    ev["ts"] = round(time.time(), 3)
    with open(os.path.join(ws, kernel.STORE, "draft.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, sort_keys=True) + "\n")
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


# The two names below are the agent harness's vocabulary, not ours: they are
# matched literally against what it sends, so they are never renamed by us.
HOOK = {"type": "command", "command": "ret hook"}
EVENTS = {"UserPromptSubmit": None,
          "PostToolUse": "Write|Edit|MultiEdit|NotebookEdit|Read|Bash"}


def install(project: str) -> dict:
    """`ret hooks`: wire the agent to the trace via .claude/settings.json.
    Idempotent — merges the two entries in, touches nothing else."""
    root = os.path.abspath(project)
    path = os.path.join(root, ".claude", "settings.json")
    settings = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    hooks = settings.setdefault("hooks", {})
    wired = []
    for name, matcher in EVENTS.items():
        entries = hooks.setdefault(name, [])
        if not any(h.get("command") == HOOK["command"]
                   for e in entries for h in e.get("hooks", [])):
            entry = {"matcher": matcher, "hooks": [dict(HOOK)]} if matcher \
                else {"hooks": [dict(HOOK)]}
            entries.append(entry)
            wired.append(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"settings": os.path.join(".claude", "settings.json"),
            "wired": wired, "status": "wired" if wired else "already wired"}
