"""hooks: the coding-agent handshake (`spec/layers.md`: agents).

`event` turns one Claude Code hook payload into a trace entry appended to
the session's draft trace (the same file `reticuli.feedback` and
`reticuli.authoring` read), or into nothing: a payload naming an event this
module does not track, a payload whose file falls outside the session
directory, and a payload whose `cwd` is not a session at all (no
`.reticuli` store there) all return `None` and write nothing.

`install` wires the handful of hook events this module needs into a
project's `.claude/settings.json`, preserving every other key already
there, and is idempotent: a second call recognizes the wiring is already
present and leaves the file untouched, byte for byte.

Stdlib only.
"""
import json
import os
import sys
import time

STORE = ".reticuli"
TRACE = ".reticuli/draft.jsonl"

HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
HOOK_COMMAND = f"{sys.executable} -m reticuli.hooks"


def _is_session(ws) -> bool:
    return bool(ws) and os.path.isdir(os.path.join(ws, STORE))


def _relative(ws: str, file_path):
    """`file_path`'s path relative to `ws`, or `None` if it names nothing
    inside `ws` -- checked by realpath, not by string prefix, so a `cwd`
    reached through a symlinked temp directory still resolves correctly."""
    if not file_path:
        return None
    ws_real = os.path.realpath(ws)
    target_real = os.path.realpath(file_path)
    rel = os.path.relpath(target_real, ws_real)
    if rel == os.curdir or rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    if os.path.isabs(rel):
        return None
    return rel.replace(os.sep, "/")


def _append(ws: str, entry: dict) -> None:
    path = os.path.join(ws, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def event(payload: dict):
    """Turn one Claude Code hook payload into a trace entry, or `None`.

    Guarded two ways before any event mapping happens: `cwd` must name a
    session (a directory with a `.reticuli` store), and a tool payload's
    file must resolve inside that session directory.
    """
    ws = payload.get("cwd")
    if not _is_session(ws):
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "ts": time.time()}
    elif name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input") or {}
        if tool == "Write":
            rel = _relative(ws, tool_input.get("file_path"))
            if rel is None:
                return None
            entry = {"event": "write", "path": rel, "ts": time.time()}
        elif tool == "Read":
            rel = _relative(ws, tool_input.get("file_path"))
            if rel is None:
                return None
            entry = {"event": "read", "path": rel, "ts": time.time()}
        elif tool == "Bash":
            cmd = tool_input.get("command")
            if not cmd:
                return None
            entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
        else:
            return None
    else:
        return None

    _append(ws, entry)
    return entry


def install(project: str) -> dict:
    """Wire this module into `project/.claude/settings.json` for every
    event in `HOOK_EVENTS`, preserving every other key and every other
    hook already configured. A re-run that finds everything already wired
    writes nothing and reports `"already wired"`."""
    path = os.path.join(project, ".claude", "settings.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.setdefault("hooks", {})
    wired = []
    for event_name in HOOK_EVENTS:
        matchers = hooks_cfg.setdefault(event_name, [])
        already = any(
            h.get("type") == "command" and h.get("command") == HOOK_COMMAND
            for m in matchers
            for h in m.get("hooks", [])
        )
        if already:
            continue
        matchers.append({"hooks": [{"type": "command", "command": HOOK_COMMAND}]})
        wired.append(event_name)

    if not wired:
        return {"status": "already wired"}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


def main() -> int:
    """Entry point for the installed hook command: read one JSON payload
    from stdin, trace it if applicable, never block the agent."""
    try:
        payload = json.load(sys.stdin)
        event(payload)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
