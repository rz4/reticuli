"""Advise whether a traced work session has an apparent verdict."""
import json
import os

TRACE = '.reticuli/draft.jsonl'


def advise(workspace):
    path = os.path.join(workspace, TRACE)
    try:
        with open(path, encoding='utf-8') as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    commands = [e.get('cmd') for e in events if e.get('event') == 'bash' and e.get('cmd')]
    return {'sealable': bool(commands), 'events': len(events), 'gates': commands}
