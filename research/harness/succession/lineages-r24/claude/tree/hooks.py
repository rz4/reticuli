"""hooks: the coding-agent handshake (spec/layers.md "agents").

Claude Code's hook payloads (`hook_event_name`, `tool_name`, `tool_input`,
`cwd`) become the session-trace events the authoring layer already reads
from `.reticuli/draft.jsonl` (`reticuli.feedback`, `reticuli.authoring`):
a prompt (`UserPromptSubmit`), a candidate generated-output write
(`PostToolUse` on the `Write` tool), and a gate run (`PostToolUse` on the
`Bash` tool). A `Read` is recognized and reported but never recorded --
authoring treats a traced read as a declared pinned input by default, and
a tool merely glancing at a file must not silently pin it.

A payload whose `cwd` names no tracked session (no `.reticuli` directory)
is a no-op, and a payload naming a path outside the session is ignored --
neither ever touches the trace. `install` wires this module's hook command
into a project's Claude Code settings idempotently: it adds only the hook
events it owns and otherwise leaves the settings file untouched. Stdlib
only.
"""
import json
import os
import sys
import time

STORE = ".reticuli"
TRACE = ".reticuli/draft.jsonl"
SETTINGS = ".claude/settings.json"
HOOK_COMMAND = "python3 -m reticuli.hooks"
HOOK_EVENTS = ("UserPromptSubmit", "PostToolUse")


# -- payload -> trace event ---------------------------------------------

def _session_root(payload: dict):
    """`payload`'s `cwd`, if it names a directory already tracking a
    session (`.reticuli/` present) -- else `None`."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    if not os.path.isdir(os.path.join(cwd, STORE)):
        return None
    return cwd


def _relpath_in_session(session: str, path):
    """`path` relative to `session`, or `None` if it is not a string or
    resolves outside the session (symlinks aside, same rule the kernel's
    own path boundary applies: identity must not depend on what a
    particular host's filesystem is willing to resolve)."""
    if not isinstance(path, str) or not path:
        return None
    base = os.path.realpath(session)
    resolved = os.path.realpath(path) if os.path.isabs(path) \
        else os.path.realpath(os.path.join(base, path))
    if resolved == base or not resolved.startswith(base + os.sep):
        return None
    return os.path.relpath(resolved, base)


def _append(session: str, ev: dict) -> dict:
    path = os.path.join(session, TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, sort_keys=True))
        f.write("\n")
    return ev


def event(payload: dict):
    """One Claude Code hook payload, mapped to a trace event and recorded
    -- or `None` where there is nothing to record: an unrecognized hook,
    no tracked session, or a path outside it."""
    session = _session_root(payload)
    if session is None:
        return None

    name = payload.get("hook_event_name")
    if name == "UserPromptSubmit":
        return _append(session, {
            "event": "prompt", "prompt": payload.get("prompt"), "ts": time.time(),
        })

    if name != "PostToolUse":
        return None

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool == "Write":
        rel = _relpath_in_session(session, tool_input.get("file_path"))
        if rel is None:
            return None
        return _append(session, {"event": "write", "path": rel, "ts": time.time()})

    if tool == "Read":
        rel = _relpath_in_session(session, tool_input.get("file_path"))
        if rel is None:
            return None
        return {"event": "read", "path": rel, "ts": time.time()}

    if tool == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str):
            return None
        return _append(session, {"event": "bash", "cmd": cmd, "ts": time.time()})

    return None


# -- wiring: install the hook command into a project's settings ---------

def _already_wired(entries) -> bool:
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for h in (entry.get("hooks") or []):
            if isinstance(h, dict) and h.get("type") == "command" \
                    and h.get("command") == HOOK_COMMAND:
                return True
    return False


def install(proj: str) -> dict:
    """Wire this handshake into `proj`'s `.claude/settings.json`:
    idempotent, touching only the hook events this module owns, and
    leaving every other setting -- and every other hook already wired for
    the same event -- untouched."""
    path = os.path.join(proj, SETTINGS)
    settings = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            settings = json.load(f)

    hooks_cfg = dict(settings.get("hooks") or {})
    wired = []
    for ev_name in HOOK_EVENTS:
        entries = hooks_cfg.get(ev_name)
        if _already_wired(entries):
            continue
        entries = list(entries) if isinstance(entries, list) else []
        entries.append({"hooks": [{"type": "command", "command": HOOK_COMMAND}]})
        hooks_cfg[ev_name] = entries
        wired.append(ev_name)

    if not wired:
        return {"status": "already wired", "wired": []}

    settings["hooks"] = hooks_cfg
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
        f.write("\n")
    return {"status": "wired", "wired": wired}


# -- entry point for the installed hook command --------------------------

def main() -> None:
    """Read one JSON hook payload from stdin and record it; a hook's
    stdout is otherwise interpreted by its caller, so this emits nothing."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return
    event(payload)


if __name__ == "__main__":
    main()
