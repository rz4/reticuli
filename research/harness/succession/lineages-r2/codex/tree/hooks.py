"""Claude Code hooks for recording a claim authoring session."""
from __future__ import annotations

import json
import os
import shlex
import sys
import time

from . import kernel
from ._util import safe_path


TRACE = ".reticuli/draft.jsonl"
EVENTS = ("UserPromptSubmit", "PostToolUse")


def _relative_file(cwd, name):
    """Return a session-relative path, or None for a path outside it."""
    if not isinstance(name, str) or not name:
        return None
    root = os.path.realpath(cwd)
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath((root, path)) != root or path == root:
        return None
    relative = os.path.relpath(path, root).replace(os.sep, "/")
    try:
        safe_path(root, relative)
    except kernel.ClaimError:
        return None
    return relative


def event(payload):
    """Append one recognized hook event when its session exists."""
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(os.path.join(cwd, ".reticuli")):
        return None
    kind = payload.get("hook_event_name")
    result = None
    if kind == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            result = {"event": "prompt", "prompt": prompt}
    elif kind == "PostToolUse":
        tool = payload.get("tool_name")
        inputs = payload.get("tool_input")
        if not isinstance(inputs, dict):
            return None
        if tool in ("Write", "Edit", "MultiEdit", "Read"):
            relative = _relative_file(cwd, inputs.get("file_path"))
            if relative is not None:
                result = {"event": "read" if tool == "Read" else "write",
                          "path": relative}
        elif tool == "Bash" and isinstance(inputs.get("command"), str):
            result = {"event": "bash", "cmd": inputs["command"]}
    if result is None:
        return None
    result["ts"] = time.time()
    # A read of a file that was never present is useful to the hook caller,
    # but cannot become a declared, pinned input of the authored claim.
    if result["event"] == "read" and not os.path.isfile(safe_path(cwd, result["path"])):
        return result
    path = safe_path(cwd, TRACE)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")
    return result


def install(project):
    """Wire the two event families while preserving unrelated settings."""
    settings = os.path.join(project, ".claude", "settings.json")
    try:
        with open(settings, encoding="utf-8") as stream:
            document = json.load(stream)
    except FileNotFoundError:
        document = {}
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read Claude settings: {exc}") from exc
    if not isinstance(document, dict):
        raise kernel.ClaimError("Claude settings must be a JSON object")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise kernel.ClaimError("Claude hooks must be a JSON object")
    command = f"{shlex.quote(sys.executable)} -m reticuli.hooks"
    changed = False
    for name in EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise kernel.ClaimError(f"Claude {name} hooks must be a JSON array")
        if any(isinstance(group, dict) and any(
                isinstance(hook, dict) and hook.get("command") == command
                for hook in group.get("hooks", [])) for group in entries):
            continue
        group = {"hooks": [{"type": "command", "command": command}]}
        if name == "PostToolUse":
            group["matcher"] = "Write|Edit|MultiEdit|Read|Bash"
        entries.append(group)
        changed = True
    if changed:
        os.makedirs(os.path.dirname(settings), exist_ok=True)
        with open(settings, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return {"status": "wired" if changed else "already wired", "wired": list(EVENTS)}


def main():
    try:
        event(json.load(sys.stdin))
    except (ValueError, OSError) as exc:
        print(f"reticuli hook: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
