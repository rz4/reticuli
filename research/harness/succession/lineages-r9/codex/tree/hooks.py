"""Claude Code hooks that record an active workspace's authoring trace."""

from __future__ import annotations

import json
import os
import sys
import time

TRACE = os.path.join('.reticuli', 'draft.jsonl')
COMMAND = 'python3 -m reticuli.hooks'
EVENTS = ('UserPromptSubmit', 'PostToolUse')


def _session(payload):
    cwd = payload.get('cwd')
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    workspace = os.path.realpath(cwd)
    return workspace if os.path.isdir(os.path.join(workspace, '.reticuli')) else None


def _relative_file(workspace, value):
    if not isinstance(value, str) or not value:
        return None
    absolute = os.path.realpath(value if os.path.isabs(value)
                            else os.path.join(workspace, value))
    try:
        if os.path.commonpath((workspace, absolute)) != workspace:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(absolute, workspace)
    return relative if relative != '.' else None


def event(payload):
    """Translate one hook payload and append its event, if a session exists."""
    if not isinstance(payload, dict):
        return None
    workspace = _session(payload)
    if workspace is None:
        return None

    hook = payload.get('hook_event_name')
    row = None
    if hook == 'UserPromptSubmit':
        prompt = payload.get('prompt')
        if isinstance(prompt, str):
            row = {'event': 'prompt', 'prompt': prompt}
    elif hook == 'PostToolUse':
        tool = payload.get('tool_name')
        inputs = payload.get('tool_input')
        if not isinstance(inputs, dict):
            return None
        if tool in ('Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Read'):
            path = _relative_file(workspace, inputs.get('file_path') or
                                  inputs.get('notebook_path'))
            if path is not None:
                row = {'event': 'read' if tool == 'Read' else 'write',
                       'path': path}
        elif tool == 'Bash':
            command = inputs.get('command')
            if isinstance(command, str) and command:
                row = {'event': 'bash', 'cmd': command}

    if row is None:
        return None
    row['ts'] = time.time()
    # A tool payload can name a read that produced no workspace file. Keep
    # the translated event, but only trace files authoring can later pin.
    if row['event'] == 'read' and not os.path.isfile(
            os.path.join(workspace, row['path'])):
        return row
    with open(os.path.join(workspace, TRACE), 'a', encoding='utf-8') as target:
        target.write(json.dumps(row, sort_keys=True) + '\n')
    return row


def install(project):
    """Wire the two Claude hook events while retaining other settings."""
    settings_path = os.path.join(os.fspath(project), '.claude', 'settings.json')
    try:
        with open(settings_path, encoding='utf-8') as source:
            settings = json.load(source)
    except FileNotFoundError:
        settings = {}
    if not isinstance(settings, dict):
        raise ValueError('Claude settings must be a JSON object')
    hooks = settings.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Claude hooks must be a JSON object')

    wired = []
    for name in EVENTS:
        entries = hooks.setdefault(name, [])
        if not isinstance(entries, list):
            raise ValueError(f'Claude {name} hooks must be a list')
        found = any(isinstance(group, dict) and any(
            isinstance(hook, dict) and hook.get('command') == COMMAND
            for hook in group.get('hooks', [])) for group in entries)
        if not found:
            entries.append({'hooks': [{'type': 'command', 'command': COMMAND}]})
            wired.append(name)

    if not wired:
        return {'status': 'already wired', 'wired': list(EVENTS)}
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, 'w', encoding='utf-8') as target:
        json.dump(settings, target, indent=2)
        target.write('\n')
    return {'status': 'wired', 'wired': wired}


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    event(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
