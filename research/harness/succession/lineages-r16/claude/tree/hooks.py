"""hooks: the coding-agent handshake (`spec/layers.md`).

Claude Code calls a hook script with one JSON payload per event, on the
shapes it defines (`hook_event_name`, `cwd`, and event-specific fields like
`prompt` or `tool_input`). `event` turns one such payload into a trace
event, or into nothing: a payload naming no session (`cwd` holds no
`.reticuli/`) is a no-op, and a file-touching payload naming a path outside
that session is ignored, never partially recorded.

Only the events the authoring layer's trace format actually consumes --
`prompt`, `write`, `bash` (`reticuli.authoring`'s `TRACE` file: `path` for
writes, `cmd` for bash, both timestamped) -- are appended there. A `Read` is
still classified and returned, for a caller that wants to observe it, but
never traced: an agent may read a file that was never written and does not
exist under the session, and recording it as a candidate pinned input would
hand `build_claim` a path it cannot copy.

`install` wires this script into a project's `.claude/settings.json` hook
config for `UserPromptSubmit` and `PostToolUse`, idempotently, touching
nothing else already in that file.
"""
import json
import os
import sys
import time

from reticuli.kernel import STORE

TRACE = os.path.join(STORE, "draft.jsonl")

HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
HOOK_COMMAND = "python3 -m reticuli.hooks"


def _is_session(cwd) -> bool:
    return bool(cwd) and os.path.isdir(os.path.join(cwd, STORE))


def _relative_within(cwd: str, file_path) -> str:
    """`file_path`'s path relative to `cwd`, or `None` if it is missing,
    equal to `cwd` itself, or escapes it."""
    if not file_path:
        return None
    cwd_real = os.path.realpath(cwd)
    target_real = os.path.realpath(file_path)
    if target_real == cwd_real:
        return None
    try:
        common = os.path.commonpath([cwd_real, target_real])
    except ValueError:
        return None
    if common != cwd_real:
        return None
    return os.path.relpath(target_real, cwd_real).replace(os.sep, "/")


def _trace(cwd: str, entry: dict) -> None:
    """Append one timestamped event to `cwd`'s session trace."""
    record = dict(entry)
    record["ts"] = time.time()
    path = os.path.join(cwd, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def event(payload: dict):
    """One hook payload, classified -- or `None` if it names no session,
    or a path outside one, or an event this layer does not recognize."""
    cwd = payload.get("cwd")
    if not _is_session(cwd):
        return None

    name = payload.get("hook_event_name")

    if name == "UserPromptSubmit":
        result = {"event": "prompt", "prompt": payload.get("prompt", "")}
        _trace(cwd, result)
        return result

    if name == "PostToolUse":
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input") or {}

        if tool == "Bash":
            result = {"event": "bash", "cmd": tool_input.get("command", "")}
            _trace(cwd, result)
            return result

        if tool == "Write":
            path = _relative_within(cwd, tool_input.get("file_path"))
            if path is None:
                return None
            result = {"event": "write", "path": path}
            _trace(cwd, result)
            return result

        if tool == "Read":
            path = _relative_within(cwd, tool_input.get("file_path"))
            if path is None:
                return None
            return {"event": "read", "path": path}

        return None

    return None


def _wired(groups, command: str = HOOK_COMMAND) -> bool:
    for group in groups or []:
        for h in group.get("hooks", []):
            if h.get("type") == "command" and h.get("command") == command:
                return True
    return False


def install(project_dir: str) -> dict:
    """Wire this hook into `project_dir`'s `.claude/settings.json` for
    every event in `HOOK_EVENTS`, leaving the rest of the file untouched.
    Idempotent: a second call changes nothing and reports as much."""
    claude_dir = os.path.join(project_dir, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")

    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.setdefault("hooks", {})
    missing = [ev for ev in HOOK_EVENTS if not _wired(hooks_cfg.get(ev))]
    if not missing:
        return {"status": "already wired"}

    for ev in missing:
        hooks_cfg.setdefault(ev, []).append(
            {"matcher": "", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}
        )

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return {"wired": missing}


def main() -> None:
    """Entry point for `HOOK_COMMAND`: one JSON payload on stdin, classified
    and traced; nothing is ever printed back to the agent."""
    payload = json.load(sys.stdin)
    event(payload)


if __name__ == "__main__":
    main()
