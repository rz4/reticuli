"""Claude Code hooks that turn an active workspace session into a trace."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time


TRACE = os.path.join('.reticuli', 'draft.jsonl')
HOOK_COMMAND = f'{shlex.quote(sys.executable)} -m reticuli.hooks'


def _session(payload):
    cwd = payload.get('cwd')
    if not isinstance(cwd, str) or not os.path.isdir(os.path.join(cwd, '.reticuli')):
        return None
    return os.path.realpath(cwd)


def _relative_file(workspace, value):
    if not isinstance(value, str) or not value:
        return None
    path = value if os.path.isabs(value) else os.path.join(workspace, value)
    path = os.path.realpath(path)
    try:
        if os.path.commonpath((workspace, path)) != workspace or path == workspace:
            return None
    except ValueError:
        return None
    return os.path.relpath(path, workspace).replace(os.sep, '/')


def event(payload):
    """Append a recognized hook event, or return None outside a session."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    name = payload.get('hook_event_name')
    row = None
    if name == 'UserPromptSubmit':
        prompt = payload.get('prompt')
        if isinstance(prompt, str):
            row = {'event': 'prompt', 'prompt': prompt}
    elif name == 'PostToolUse':
        tool = payload.get('tool_name')
        args = payload.get('tool_input')
        if not isinstance(args, dict):
            return None
        if tool in ('Write', 'Edit', 'MultiEdit', 'Read'):
            path = _relative_file(workspace, args.get('file_path'))
            if path is not None:
                row = {'event': 'read' if tool == 'Read' else 'write', 'path': path}
        elif tool == 'Bash' and isinstance(args.get('command'), str):
            row = {'event': 'bash', 'cmd': args['command']}

    if row is None:
        return None
    # A reported read can name a missing file. It is still a read event for
    # the caller, but it cannot become a pinned input to a sealed claim.
    if row['event'] == 'read' and not os.path.isfile(os.path.join(workspace, row['path'])):
        return row
    row['ts'] = time.time()
    with open(os.path.join(workspace, TRACE), 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def install(project):
    """Add the two hook entries while preserving existing Claude settings."""
    settings_dir = os.path.join(project, '.claude')
    os.makedirs(settings_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, 'settings.json')
    if os.path.isfile(settings_path):
        with open(settings_path, encoding='utf-8') as stream:
            settings = json.load(stream)
    else:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError('Claude settings must be a JSON object')
    hooks = settings.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Claude hooks must be a JSON object')

    wired = []
    changed = False
    for name in ('UserPromptSubmit', 'PostToolUse'):
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f'Claude {name} hooks must be an array')
        present = any(isinstance(entry, dict) and any(
            isinstance(hook, dict) and hook.get('command') == HOOK_COMMAND
            for hook in entry.get('hooks', []) if isinstance(entry.get('hooks'), list))
            for entry in entries)
        if not present:
            entries.append({'hooks': [{'type': 'command', 'command': HOOK_COMMAND}]})
            changed = True
        wired.append(name)
    if changed:
        with open(settings_path, 'w', encoding='utf-8') as stream:
            json.dump(settings, stream, indent=2)
            stream.write('\n')
    return {'status': 'wired' if changed else 'already wired', 'wired': wired}


def main():
    try:
        event(json.load(sys.stdin))
    except (OSError, ValueError):
        pass


if __name__ == '__main__':
    main()
