"""The coding-agent handshake (`spec/layers.md`'s agents layer).

`event` turns one Claude Code hook payload into a `.reticuli/draft.jsonl`
trace entry (`prompt`, `write`, `read`, `bash`) that the authoring layer
(`feedback.advise`, `authoring.build_claim`) reads back later -- the same
trace vocabulary, written incrementally as a session runs instead of all
at once. Two guards apply before any mapping: no session (no `.reticuli/`
directory at the hook's `cwd`) is a no-op, and a path outside the session
directory is ignored rather than recorded, so a tool touching the rest of
the filesystem cannot smuggle an unconfined path into a future claim.

A `read` event is recorded only when the named file currently exists --
an explicit `read` trace entry is trusted as given by the authoring layer
(it never re-checks the filesystem), so a hook that recorded a read of a
file that was never actually there would hand `build_claim` a pinned
input it cannot copy. A `write` event carries no such requirement: the
tool is creating the file, which commonly does not yet exist at hook time.

`install` wires the two hook events this layer consumes into a project's
Claude Code settings (`.claude/settings.json`), idempotently and without
disturbing any other key already there.

Stdlib only.
"""
import json
import os
import sys
import time

TRACE = ".reticuli/draft.jsonl"

HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")
_HOOK_COMMAND = f"{sys.executable} -m reticuli.hooks"


def _has_session(cwd) -> bool:
    return bool(cwd) and os.path.isdir(os.path.join(cwd, ".reticuli"))


def _relative(cwd: str, file_path) -> str:
    """`file_path` relative to `cwd`, or `None` if absent or outside it."""
    if not file_path:
        return None
    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(cwd))
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return None
    return rel


def _append(cwd: str, entry: dict) -> None:
    path = os.path.join(cwd, TRACE)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def event(payload: dict):
    """Map one hook payload to a trace entry, record it, and return it.
    `None` when the payload is not a session event this layer tracks."""
    cwd = payload.get("cwd")
    if not _has_session(cwd):
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        entry = {"event": "prompt", "prompt": payload.get("prompt", ""),
                 "ts": time.time()}
        _append(cwd, entry)
        return entry

    if name != "PostToolUse":
        return None

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = _relative(cwd, tool_input.get("file_path"))
        if path is None:
            return None
        entry = {"event": "write", "path": path, "ts": time.time()}
        _append(cwd, entry)
        return entry

    if tool == "Read":
        path = _relative(cwd, tool_input.get("file_path"))
        if path is None:
            return None
        entry = {"event": "read", "path": path, "ts": time.time()}
        if os.path.isfile(os.path.join(cwd, path)):
            _append(cwd, entry)
        return entry

    if tool == "Bash":
        entry = {"event": "bash", "cmd": tool_input.get("command", ""),
                 "ts": time.time()}
        _append(cwd, entry)
        return entry

    return None


# -- wiring: .claude/settings.json ------------------------------------------

def _hook_entry() -> dict:
    return {"matcher": "", "hooks": [{"type": "command", "command": _HOOK_COMMAND}]}


def _is_wired(entries: list) -> bool:
    return any(
        h.get("type") == "command" and h.get("command") == _HOOK_COMMAND
        for entry in entries for h in entry.get("hooks", [])
    )


def install(proj: str) -> dict:
    """Wire the agent hooks into `proj`'s `.claude/settings.json`,
    idempotently and without touching any other key already there."""
    settings_path = os.path.join(proj, ".claude", "settings.json")
    if os.path.isfile(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks_cfg = settings.get("hooks", {})
    if all(_is_wired(hooks_cfg.get(name, [])) for name in HOOK_EVENTS):
        return {"status": "already wired"}

    wired = []
    for name in HOOK_EVENTS:
        entries = hooks_cfg.setdefault(name, [])
        if not _is_wired(entries):
            entries.append(_hook_entry())
            wired.append(name)
    settings["hooks"] = hooks_cfg

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return {"status": "wired", "wired": wired}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    event(payload)


if __name__ == "__main__":
    main()
