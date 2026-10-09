"""hooks: the coding-agent handshake (spec/layers.md).

Claude Code fires a hook with a JSON payload for things that happen in a
session -- a prompt submitted, a tool finishing. `event` turns a payload
into one line of the session's draft trace (`authoring.TRACE`), the same
trace `feedback.advise` and `authoring.build_claim` read: a prompt, a
file write, a file read, a bash command. Two guards apply before any
bytes move: a payload whose `cwd` carries no `.reticuli` directory names
no session, so it is a no-op; a payload whose target escapes that
session directory is outside this tool's business, so it is ignored, not
refused -- a hook fires for the whole machine, not just the claim being
built.

A "read" is logged without a `path` when the referenced file is not
actually present: a traced read is a candidate pinned input only when it
names a real, present file (spec/identity.md's exact-existence rule for
anything identity may depend on), and omitting the path here is where
that rule is enforced -- `authoring.py`'s classifier has no existence
check of its own for a traced read.

`install` wires this module's command into a project's Claude Code
settings for the two events above, idempotently and without disturbing
anything else already in the file.
"""
import json
import os
import sys
import time

TRACE = ".reticuli/draft.jsonl"

_SETTINGS_REL = os.path.join(".claude", "settings.json")
_HOOK_COMMAND = f"{sys.executable} -m reticuli.hooks"
_HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


# -- turning one hook payload into one trace event --------------------------

def _session_dir(cwd):
    if isinstance(cwd, str) and cwd and os.path.isdir(os.path.join(cwd, ".reticuli")):
        return cwd
    return None


def _relative(ws: str, path) -> str:
    """`path` relative to `ws`, or None if it is missing or escapes `ws`."""
    if not isinstance(path, str) or not path:
        return None
    rel = os.path.relpath(path, ws)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel


def _append(ws: str, record: dict) -> None:
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True))
        f.write("\n")


def event(payload: dict):
    """Turn one hook payload into a trace event appended to the session's
    draft trace; returns the event recorded, or None for a no-op."""
    ws = _session_dir(payload.get("cwd"))
    if ws is None:
        return None

    name = payload.get("hook_event_name")
    record = None

    if name == "UserPromptSubmit":
        record = {"event": "prompt", "prompt": payload.get("prompt", ""),
                  "ts": time.time()}

    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}

        if tool == "Write":
            rel = _relative(ws, tool_input.get("file_path"))
            if rel is None:
                return None
            record = {"event": "write", "path": rel, "ts": time.time()}

        elif tool == "Read":
            file_path = tool_input.get("file_path")
            rel = _relative(ws, file_path)
            if rel is None:
                return None
            record = {"event": "read", "ts": time.time()}
            if os.path.isfile(file_path):
                record["path"] = rel

        elif tool == "Bash":
            command = tool_input.get("command")
            record = {"event": "bash", "cmd": command if isinstance(command, str) else "",
                      "ts": time.time()}

    if record is None:
        return None
    _append(ws, record)
    return record


# -- wiring the handshake into a project's Claude Code settings -------------

def _command_present(entries, command: str) -> bool:
    for matcher in entries or ():
        if not isinstance(matcher, dict):
            continue
        for h in matcher.get("hooks") or ():
            if isinstance(h, dict) and h.get("command") == command:
                return True
    return False


def install(proj: str) -> dict:
    """Wire this module's hook command into `proj`'s `.claude/settings.json`
    for every event `event()` understands. Idempotent: a second call makes
    no change and reports `"already wired"`; any other key already in the
    file, and any hook already wired for another command, survives untouched."""
    path = os.path.join(proj, _SETTINGS_REL)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.get("hooks")
    if not isinstance(hooks_cfg, dict):
        hooks_cfg = {}

    if all(_command_present(hooks_cfg.get(name), _HOOK_COMMAND) for name in _HOOK_EVENTS):
        return {"status": "already wired", "wired": []}

    wired = []
    for name in _HOOK_EVENTS:
        entries = list(hooks_cfg.get(name) or [])
        if not _command_present(entries, _HOOK_COMMAND):
            entries.append({"matcher": "", "hooks": [{"type": "command", "command": _HOOK_COMMAND}]})
            wired.append(name)
        hooks_cfg[name] = entries
    settings["hooks"] = hooks_cfg

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


# -- the command `install` wires: read one payload from stdin, trace it ----

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if isinstance(payload, dict):
        event(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
