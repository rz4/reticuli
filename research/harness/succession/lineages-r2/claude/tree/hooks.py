"""hooks: the coding-agent handshake (spec/layers.md).

`event` turns one Claude Code hook payload into a trace event appended to
the session's own draft trace (`.reticuli/draft.jsonl` -- the same file
`authoring.propose` and `feedback.advise` read), or into nothing at all:
a payload whose `cwd` is not a session (no `.reticuli/` there) is a no-op,
and a payload naming a path outside the session is ignored, never traced.
A `read` or `write` payload is still classified and returned even when the
named file does not yet exist on disk (a hook can fire before the tool's
own effect lands), but only a path that is actually there is durable
enough to enter the trace -- an attempt with nothing behind it leaves no
residue for `authoring.propose` to mistake for pinned content.

`install` wires this handshake into a project's Claude Code settings
(`.claude/settings.json`): idempotent, and every other key already there
survives untouched.

Stdlib only.
"""
import json
import os
import sys
import time

from . import _util, kernel

STORE = kernel.STORE
TRACE = ".reticuli/draft.jsonl"

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_READ_TOOLS = frozenset({"Read", "NotebookRead"})

CLAUDE_DIR = ".claude"
SETTINGS = "settings.json"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


# ---------------------------------------------------------------------------
# event: hook payload -> trace event, or None
# ---------------------------------------------------------------------------

def _is_session(cwd: str) -> bool:
    return os.path.isdir(os.path.join(cwd, STORE))


def _relpath(cwd: str, path: str):
    """`path` relative to `cwd`, POSIX-style, or None if it escapes `cwd`."""
    rel = os.path.relpath(path, cwd)
    parts = rel.split(os.sep)
    if rel == os.curdir or parts[0] == os.pardir or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, "/")


def _trace_append(cwd: str, entry: dict) -> None:
    _util.locked_append(os.path.join(cwd, TRACE), json.dumps(entry, sort_keys=True))


def event(payload: dict):
    """Turn one Claude Code hook payload into a trace event; `None` if the
    payload is a no-op (no session at `cwd`), escapes the session, or
    simply isn't one of the kinds this handshake understands."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not _is_session(cwd):
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "text": payload.get("prompt", ""), "ts": time.time()}
        _trace_append(cwd, entry)
        return entry

    if name != "PostToolUse":
        return None

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str):
            return None
        entry = {"event": "bash", "cmd": cmd, "ts": time.time()}
        _trace_append(cwd, entry)
        return entry

    if tool in _WRITE_TOOLS or tool in _READ_TOOLS:
        file_path = tool_input.get("file_path")
        if not isinstance(file_path, str):
            return None
        rel = _relpath(cwd, file_path)
        if rel is None:
            return None
        entry = {"event": "write" if tool in _WRITE_TOOLS else "read",
                  "path": rel, "ts": time.time()}
        if os.path.isfile(file_path):
            _trace_append(cwd, entry)
        return entry

    return None


# ---------------------------------------------------------------------------
# install: wire the handshake into a project's Claude Code settings
# ---------------------------------------------------------------------------

def _hook_command() -> str:
    return f"{sys.executable} -m reticuli.hooks"


def _hook_entry() -> dict:
    return {"type": "command", "command": _hook_command()}


def _already_wired(groups) -> bool:
    for group in groups:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []):
            if isinstance(h, dict) and h.get("type") == "command" \
                    and h.get("command") == _hook_command():
                return True
    return False


def install(project_dir: str) -> dict:
    """Wire the handshake into `project_dir`'s `.claude/settings.json`:
    idempotent (a second call changes nothing), and every other key
    already in the file -- and every other hook already wired -- survives
    untouched."""
    settings_path = os.path.join(project_dir, CLAUDE_DIR, SETTINGS)
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.setdefault("hooks", {})
    wired = []
    for name in HOOK_EVENTS:
        groups = hooks_cfg.get(name, [])
        if _already_wired(groups):
            continue
        groups = list(groups) + [{"hooks": [_hook_entry()]}]
        hooks_cfg[name] = groups
        wired.append(name)

    if not wired:
        return {"status": "already wired", "wired": []}

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


# ---------------------------------------------------------------------------
# entry point: Claude Code invokes this as a hook command
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return 0
    try:
        event(payload)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
